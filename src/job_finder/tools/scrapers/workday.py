"""Workday ATS scraper — searches corporate career portals via public JSON API.

Many large employers (NVIDIA, Salesforce, Netflix, Adobe, etc.) run their
career sites on Workday. The Workday career site exposes a public JSON
search endpoint at ``/wday/cxs/{tenant}/{site_id}/jobs`` that requires no
authentication and returns structured job data including full descriptions.

This scraper searches multiple Workday-powered career portals in parallel,
filters by role keywords and location, and returns results in Questboard's
standard job dict format.

Employer configs are loaded from ``config/workday_employers.yaml``.
"""

from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers.workday_builtin_employers import _BUILTIN_EMPLOYERS
from job_finder.tools.scrapers._utils import (
    PROTECTED_ROW_KEY,
    WATCHLIST_TIMEOUT,
    _clean_company_name,
    _match_roles,
    _norm_company_key,
    cap_with_protected,
    rank_by_relevance,
)

logger = logging.getLogger(__name__)

# Tight per-request timeout to match the other ATS scrapers (Ashby/Lever/
# Greenhouse use 5s). Workday's API is a touch heavier, so 8s — but well under
# the old 20s, which let one hung enterprise tenant blow past run_scrapers'
# 60s per-scraper cap (serial detail GETs × the per-posting loop) and starve
# the shared scraper pool of time better spent on startup/crypto sources.
_TIMEOUT = 8
# Employers use independent Workday tenants/hosts. Twelve workers keeps each
# tenant's request stream unchanged while avoiding four serial waves across
# the 20+ configured employers. The previous six-worker ceiling made Workday
# the slowest healthy source in live runs (often 60-80 seconds).
_MAX_EMPLOYER_WORKERS = 12
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Employer registry
# ---------------------------------------------------------------------------

_EMPLOYERS: dict[str, dict] | None = None
_SEEN_API_ERRORS: set[tuple[str, int | str]] = set()


def _load_employers() -> dict[str, dict]:
    """Load employer configs from YAML, cached after first call."""
    global _EMPLOYERS
    if _EMPLOYERS is not None:
        return _EMPLOYERS

    yaml_path = Path(__file__).resolve().parents[2] / "config" / "workday_employers.yaml"
    if not yaml_path.exists():
        logger.warning("workday_employers.yaml not found at %s — using built-in defaults", yaml_path)
        _EMPLOYERS = _BUILTIN_EMPLOYERS
        return _EMPLOYERS

    try:
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        _EMPLOYERS = data.get("employers", {})
        logger.info("Loaded %d Workday employers from %s", len(_EMPLOYERS), yaml_path)
    except Exception as e:
        logger.warning("Failed to load workday_employers.yaml: %s — using built-ins", e)
        _EMPLOYERS = _BUILTIN_EMPLOYERS

    return _EMPLOYERS




# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Convert HTML job descriptions to clean plain text."""

    _BLOCK_TAGS = frozenset(("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"))

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip = True
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")
        if tag == "li":
            self._parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
        elif tag in ("p", "div", "li", "tr"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.get_text()


# ---------------------------------------------------------------------------
# Workday CXS API
# ---------------------------------------------------------------------------

def _api_search(
    employer: dict,
    query: str,
    limit: int = 20,
    offset: int = 0,
    timeout: int | float | None = None,
) -> dict | None:
    """POST to the Workday CXS search endpoint. Returns parsed JSON or None."""
    url = f"{employer['base_url']}/wday/cxs/{employer['tenant']}/{employer['site_id']}/jobs"
    payload = {
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": query,
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": _UA,
            },
            timeout=timeout if timeout is not None else _TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        status = getattr(getattr(e, "response", None), "status_code", "request")
        key = (str(employer.get("name", "?")), status)
        noisy_but_expected = {401, 403, 404, 422}
        log_fn = logger.debug if status in noisy_but_expected else logger.warning
        if key not in _SEEN_API_ERRORS:
            _SEEN_API_ERRORS.add(key)
            log_fn("Workday API error for %s (%s): %s", employer.get("name", "?"), status, e)
        else:
            logger.debug("Workday API error for %s (%s): %s", employer.get("name", "?"), status, e)
        return None


def _api_detail(
    employer: dict,
    external_path: str,
    timeout: int | float | None = None,
) -> dict | None:
    """GET full job detail from the Workday CXS endpoint."""
    url = f"{employer['base_url']}/wday/cxs/{employer['tenant']}/{employer['site_id']}{external_path}"
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": _UA},
            timeout=timeout if timeout is not None else _TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug("Workday detail fetch failed for %s: %s", external_path, e)
        return None


# ---------------------------------------------------------------------------
# Role matching
# ---------------------------------------------------------------------------

def _matches_roles(
    title: str,
    roles: list[str] | None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> bool:
    """Check if a job title is relevant to the target roles.

    Shares `_match_roles` semantics with the other ATS scrapers, then keeps
    the historical broad fallback so recall never drops below the old gate;
    rank_by_relevance decides who survives the caps.
    """
    if not roles:
        return True
    if _match_roles(
        title, roles, match_mode=match_mode, include_founding=include_founding,
    ):
        return True
    t = title.lower()
    # Broad fallback — universal seniority and role keywords (cross-industry)
    broad = [
        "senior", "staff", "principal", "lead", "junior", "associate",
        "director", "head of", "vp ", "chief ", "founding",
        "manager", "supervisor", "coordinator",
        "engineer", "analyst", "specialist", "consultant", "architect",
        "designer", "developer", "scientist", "researcher", "strategist",
        "advisor", "administrator", "operator", "planner", "producer",
        "data", "platform", "operations", "product", "project",
        "machine learning", "ml ", "ai ",
    ]
    return any(kw in t for kw in broad)


# ---------------------------------------------------------------------------
# Search one employer
# ---------------------------------------------------------------------------

def _search_employer(
    key: str,
    employer: dict,
    roles: list[str] | None,
    max_results: int,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    watchlist: bool = False,
) -> list[dict]:
    """Search a single Workday employer and return Questboard job dicts."""
    # Build search queries from roles — pick diverse representative terms
    # rather than always taking the first N, which may cluster in one category
    if roles:
        # Deduplicate base terms and take up to 6 diverse queries
        seen_bases: set[str] = set()
        queries: list[str] = []
        for r in roles:
            base = r.lower().split()[-2:] if len(r.split()) > 2 else r.lower().split()
            base_key = " ".join(base)
            if base_key not in seen_bases:
                seen_bases.add(base_key)
                queries.append(r)
            if len(queries) >= 6:
                break
    else:
        queries = ["software engineer"]
    timeout = WATCHLIST_TIMEOUT if watchlist else None
    seen_paths: set[str] = set()
    candidates: list[dict] = []

    for query in queries:
        data = _api_search(employer, query, limit=20, timeout=timeout)
        if not data:
            if watchlist:
                logger.warning("Workday/%s: watchlist board fetch failed", key)
            continue

        for posting in data.get("jobPostings", []):
            path = posting.get("externalPath", "")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)

            title = posting.get("title", "")
            if not _matches_roles(title, roles, match_mode, include_founding):
                continue

            candidates.append({
                "title": title,
                "location": posting.get("locationsText", ""),
                "date_posted": posting.get("postedOn", ""),
                "_path": path,
            })

    # Rank BEFORE the per-employer cap: fetch-order truncation used to cut
    # exact role matches a query happened to return late. Detail GETs run
    # only for survivors. A watchlist employer skips the per-employer cap:
    # the user named it (its rows also survive the final cap, flagged below).
    ranked = rank_by_relevance(candidates, roles)
    if not watchlist:
        ranked = ranked[:max_results]

    jobs: list[dict] = []
    for cand in ranked:
        path = cand.pop("_path")
        location = cand["location"]

        description = ""
        detail = _api_detail(employer, path, timeout=timeout)
        if detail:
            info = detail.get("jobPostingInfo", {})
            description = _html_to_text(info.get("jobDescription", ""))

        is_remote = bool(
            re.search(r"remote|anywhere|work from home", location, re.IGNORECASE)
            or (detail and detail.get("jobPostingInfo", {}).get("remoteType"))
        )

        job = {
            "title": cand["title"],
            "company": employer["name"],
            "location": location,
            "description": description[:5000],
            "url": f"{employer['base_url']}/{employer['site_id']}{path}",
            "source": "workday",
            "is_remote": is_remote,
            "date_posted": cand["date_posted"],
            "salary_min": None,
            "salary_max": None,
            "company_size": "",
        }
        if watchlist:
            job[PROTECTED_ROW_KEY] = True
        jobs.append(job)

    return jobs


# ---------------------------------------------------------------------------
# Watchlist token resolution
# ---------------------------------------------------------------------------

_WD_HOST_RE = re.compile(r"^([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com$", re.IGNORECASE)
_WD_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Za-z]{2,4}$")


def _employer_from_url(token: str) -> dict | None:
    """Derive {name, tenant, site_id, base_url} from a myworkdayjobs URL."""
    from urllib.parse import urlsplit

    raw = token.strip()
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    host = parts.netloc.lower().rsplit("@", 1)[-1].split(":")[0]
    m = _WD_HOST_RE.match(host)
    if not m:
        return None
    segments = [seg for seg in parts.path.split("/") if seg]
    if len(segments) >= 4 and segments[0].lower() == "wday" and segments[1].lower() == "cxs":
        site_id = segments[3]
    else:
        site_id = next(
            (seg for seg in segments if not _WD_LOCALE_RE.match(seg)), "",
        )
    if not site_id:
        return None
    tenant = m.group(1).lower()
    return {
        "name": _clean_company_name(tenant),
        "tenant": tenant,
        "site_id": site_id,
        "base_url": f"https://{host}",
    }


def _resolve_watchlist(
    tokens: list[str],
    employers: dict[str, dict],
) -> tuple[dict[str, dict], set[str]]:
    """Resolve watchlist tokens into queryable employers.

    Three token shapes, in resolution order: a full myworkdayjobs careers URL
    (tenant, wd host, and site come straight from it), the paste path's
    ``tenant/site_id`` token (the wd host comes from the YAML entry for that
    tenant), and a bare company name (fuzzy match on YAML key/tenant/name).
    Anything else is refused with a warning: ``{tenant}.myworkdayjobs.com``
    without the wd number does not resolve in DNS, so a bare name for an
    unregistered tenant cannot reach the CXS API and guessing hosts would
    query the wrong company.
    """
    resolved = dict(employers)
    watchlist_keys: set[str] = set()
    by_tenant = {
        str(emp.get("tenant", "")).lower(): key
        for key, emp in employers.items()
        if emp.get("tenant")
    }
    by_norm: dict[str, str] = {}
    for emp_key, emp in employers.items():
        for alias in (emp_key, emp.get("tenant", ""), emp.get("name", "")):
            norm = _norm_company_key(str(alias))
            if norm:
                by_norm.setdefault(norm, emp_key)

    unresolved_msg = (
        "Workday watchlist token %r has no employer match; paste the full "
        "myworkdayjobs careers URL or add it to workday_employers.yaml"
    )
    for raw_token in tokens:
        token = str(raw_token or "").strip()
        if not token:
            continue
        cfg = (
            _employer_from_url(token)
            if "myworkdayjobs.com" in token.lower()
            else None
        )
        if cfg:
            known = by_tenant.get(cfg["tenant"])
            if known and resolved[known].get("site_id") == cfg["site_id"]:
                watchlist_keys.add(known)
            else:
                new_key = (
                    cfg["tenant"] if cfg["tenant"] not in resolved
                    else f"{cfg['tenant']}/{cfg['site_id']}"
                )
                resolved[new_key] = cfg
                watchlist_keys.add(new_key)
            continue
        if "/" in token:
            tenant, _, site_id = token.partition("/")
            known = by_tenant.get(tenant.strip().lower())
            if known:
                if site_id and site_id != resolved[known].get("site_id"):
                    # Same tenant means same wd host; honor the pasted site.
                    resolved[token] = dict(resolved[known], site_id=site_id)
                    watchlist_keys.add(token)
                else:
                    watchlist_keys.add(known)
            else:
                logger.warning(unresolved_msg, token)
            continue
        known = by_norm.get(_norm_company_key(token))
        if known:
            watchlist_keys.add(known)
        else:
            logger.warning(unresolved_msg, token)
    return resolved, watchlist_keys


# ---------------------------------------------------------------------------
# Public scraper entry point
# ---------------------------------------------------------------------------

@register_scraper(
    name="workday",
    display_name="Workday Careers",
    url="https://myworkdayjobs.com",
    description="Search corporate career portals powered by Workday ATS",
    category="ats",
    enabled_by_default=True,
)
def search_workday(
    roles: list[str] | None = None,
    max_results: int = 50,
    watchlist_companies: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Search all configured Workday employers in parallel.

    Each employer's career portal is queried via the public Workday CXS
    JSON API. Results include full job descriptions fetched from detail
    endpoints. No browser or authentication required. Watchlist tokens
    resolve via ``_resolve_watchlist``; those employers get the watchlist
    timeout and cap-protected rows, consistent with the other ATS scrapers.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    employers = _load_employers()
    watchlist_keys: set[str] = set()
    if watchlist_companies:
        employers, watchlist_keys = _resolve_watchlist(watchlist_companies, employers)
    if not employers:
        logger.warning("No Workday employers configured")
        return []

    per_employer = max(3, max_results // len(employers))
    all_jobs: list[dict] = []

    def _run(item: tuple[str, dict]) -> list[dict]:
        key, emp = item
        try:
            return _search_employer(
                key, emp, roles, per_employer,
                match_mode=match_mode,
                include_founding=include_founding,
                watchlist=key in watchlist_keys,
            )
        except Exception as e:
            logger.warning("Workday scraper failed for %s: %s", emp.get("name", key), e)
            return []

    workers = min(len(employers), _MAX_EMPLOYER_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run, item): item[0] for item in employers.items()}
        for future in as_completed(futures):
            employer_key = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    all_jobs.extend(jobs)
                    logger.info("Workday/%s: %d jobs", employer_key, len(jobs))
            except Exception as e:
                logger.warning("Workday/%s failed: %s", employer_key, e)

    logger.info("Workday total: %d jobs from %d employers", len(all_jobs), len(employers))
    # Rank before the source cap; a user-named employer's rows are exempt.
    return cap_with_protected(all_jobs, roles, max_results)
