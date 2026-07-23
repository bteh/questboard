"""Watchlist service — company ATS discovery and profile storage.

Discovery order for a new company, most reliable first:

1. Careers-link paste-through: the user gives the board URL, we keep its
   exact token after one verification probe (``resolve_board_url``).
2. Evidence from the user's own application rows: a job_url that already
   carries a board token for this company proves the token
   (``_evidence_from_applications``).
3. Slug guessing from the company name (``_generate_slugs``), the last
   resort. Name-derived guesses miss any company whose token is not
   name-shaped, which is exactly what layers 1 and 2 cover.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, unquote, urlparse

import requests
import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_TIMEOUT = 5


class BoardUrlError(ValueError):
    """A pasted careers link could not be turned into a confirmed board.

    The message is user-facing; the API layer returns it as a 422 detail.
    """


class UnsupportedBoardUrlError(BoardUrlError):
    """The URL does not belong to any supported ATS host."""


class BoardLookupError(BoardUrlError):
    """The URL looked like a supported board but could not be confirmed."""


_SUPPORTED_BOARDS_MESSAGE = (
    "Paste a careers link from Greenhouse, Lever, Ashby, or Workday. "
    "Other job boards are not supported yet."
)


def _generate_slugs(company_name: str) -> list[str]:
    """Generate possible ATS board slugs from a company name."""
    name = company_name.strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)
    parts = name.split()
    if not parts:
        return []

    slugs: list[str] = []
    hyphenated = "-".join(parts)
    joined = "".join(parts)

    # Most likely first
    slugs.append(hyphenated)
    if joined != hyphenated:
        slugs.append(joined)

    # First word only (e.g. "Anduril Industries" → "anduril")
    if len(parts) > 1:
        slugs.append(parts[0])

    # Common suffixes
    for base in [hyphenated, joined]:
        for suffix in ["com", "inc", "hq", "io", "ai", "jobs"]:
            slugs.append(f"{base}{suffix}")
            if "-" not in base or suffix not in base:
                slugs.append(f"{base}-{suffix}")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def _try_greenhouse(slug: str) -> dict | None:
    """Check if company has a Greenhouse board. Returns metadata or None."""
    try:
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobs", [])
            if isinstance(jobs, list):
                return {
                    "ats": "greenhouse",
                    "slug": slug,
                    "job_count": len(jobs),
                    "careers_url": f"https://boards.greenhouse.io/{slug}",
                }
    except Exception:
        pass
    return None


def _try_lever(slug: str) -> dict | None:
    """Check if company has a Lever board. Returns metadata or None."""
    try:
        resp = requests.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                # Need a second request for total count (or just report 1+)
                count_resp = requests.get(
                    f"https://api.lever.co/v0/postings/{slug}?mode=json",
                    timeout=_TIMEOUT,
                )
                total = len(count_resp.json()) if count_resp.status_code == 200 else len(data)
                return {
                    "ats": "lever",
                    "slug": slug,
                    "job_count": total,
                    "careers_url": f"https://jobs.lever.co/{slug}",
                }
    except Exception:
        pass
    return None


def _try_ashby(slug: str) -> dict | None:
    """Check if company has an Ashby board. Returns metadata or None."""
    try:
        resp = requests.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobs", [])
            if isinstance(jobs, list):
                return {
                    "ats": "ashby",
                    "slug": slug,
                    "job_count": len(jobs),
                    "careers_url": f"https://jobs.ashbyhq.com/{slug}",
                }
    except Exception:
        pass
    return None


def _try_workday(careers_url: str) -> dict | None:
    """Check a Workday board via its public CXS endpoint. Returns metadata or None.

    ``careers_url`` must be ``https://<tenant>.wd<N>.myworkdayjobs.com/<site>``;
    the wd host is required because the tenant alone does not identify the
    CXS shard.
    """
    try:
        parsed = urlparse(careers_url)
        host = (parsed.netloc or "").lower()
        m = _WORKDAY_HOST_RE.match(host)
        segments = [s for s in (parsed.path or "").split("/") if s]
        if not m or not segments:
            return None
        tenant, site = m.group(1), segments[0]
        resp = requests.post(
            f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
            json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            total = data.get("total")
            if isinstance(total, int):
                return {
                    "ats": "workday",
                    "slug": f"{tenant}/{site}",
                    "job_count": total,
                    "careers_url": f"https://{host}/{site}",
                }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Careers-link paste-through
# ---------------------------------------------------------------------------

_WORKDAY_HOST_RE = re.compile(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$")
_WORKDAY_LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Za-z]{2,4}$")

# Token extraction from a company careers page that embeds a Greenhouse
# board (?gh_jid=... links). Ordered most specific first; the plain
# boards.greenhouse.io/<token> form comes last because it can also match
# path noise like /embed.
_GH_PAGE_TOKEN_RES = (
    re.compile(r"greenhouse\.io/embed/job_app\?[^\"'\s<>]*?for=([A-Za-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.IGNORECASE),
    re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)", re.IGNORECASE),
)
_GH_TOKEN_BLOCKLIST = {"embed", "job_app", "v1", "boards"}


def _greenhouse_board(token: str) -> dict:
    return {
        "ats": "greenhouse",
        "slug": token,
        "careers_url": f"https://boards.greenhouse.io/{token}",
    }


def parse_board_url(url: str) -> dict | None:
    """Recognize a supported ATS URL and extract its board token. Pure, no network.

    Returns ``{"ats", "slug", "careers_url"}`` or None. Accepted forms:

    - greenhouse: boards.greenhouse.io/<token>, job-boards.greenhouse.io/<token>,
      boards-api.greenhouse.io/v1/boards/<token>/..., embed/job_app?for=<token>,
      and any company page carrying ?gh_jid=<id> (slug comes back empty; the
      resolver fetches that page once to find the token).
    - lever: jobs.lever.co/<token>
    - ashby: jobs.ashbyhq.com/<token>
    - workday: <tenant>.wd<N>.myworkdayjobs.com/[<locale>/]<site>
    """
    raw = (url or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower().rsplit("@", 1)[-1].split(":")[0]
    if not host or "." not in host:
        return None
    segments = [unquote(seg) for seg in (parsed.path or "").split("/") if seg]
    query = parse_qs(parsed.query or "")

    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        if segments and segments[0].lower() == "embed":
            for_values = query.get("for", [])
            token = for_values[0].strip().lower() if for_values else ""
            return _greenhouse_board(token) if token else None
        if segments:
            return _greenhouse_board(segments[0].lower())
        return None

    if host == "boards-api.greenhouse.io":
        if len(segments) >= 3 and segments[0] == "v1" and segments[1] == "boards":
            return _greenhouse_board(segments[2].lower())
        return None

    gh_jid = query.get("gh_jid", [])
    if gh_jid and gh_jid[0].strip():
        # A company page hosting a Greenhouse posting. The board token is
        # not in the URL; the resolver fetches the page once to find it.
        for_values = query.get("for", [])
        token = for_values[0].strip().lower() if for_values else ""
        if token:
            return _greenhouse_board(token)
        return {"ats": "greenhouse", "slug": "", "careers_url": ""}

    if host in ("jobs.lever.co", "jobs.eu.lever.co") and segments:
        token = segments[0].lower()
        return {"ats": "lever", "slug": token, "careers_url": f"https://jobs.lever.co/{token}"}

    if host == "jobs.ashbyhq.com" and segments:
        token = segments[0].lower()
        return {"ats": "ashby", "slug": token, "careers_url": f"https://jobs.ashbyhq.com/{token}"}

    m = _WORKDAY_HOST_RE.match(host)
    if m:
        tenant = m.group(1)
        site = ""
        if len(segments) >= 4 and segments[0].lower() == "wday" and segments[1].lower() == "cxs":
            site = segments[3]
        else:
            for seg in segments:
                if _WORKDAY_LOCALE_RE.match(seg):
                    continue
                site = seg
                break
        if not site:
            return {"ats": "workday", "slug": "", "careers_url": ""}
        return {
            "ats": "workday",
            "slug": f"{tenant}/{site}",
            "careers_url": f"https://{host}/{site}",
        }

    return None


def _greenhouse_token_from_page(url: str) -> str:
    """Fetch a gh_jid company page once and pull the board token out of it."""
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        if getattr(resp, "status_code", 0) != 200:
            return ""
        html = getattr(resp, "text", "") or ""
    except Exception:
        return ""
    for pattern in _GH_PAGE_TOKEN_RES:
        m = pattern.search(html)
        if m:
            token = m.group(1).strip().lower()
            if token and token not in _GH_TOKEN_BLOCKLIST:
                return token
    return ""


def _probe_board(ats: str, slug: str, careers_url: str = "") -> dict | None:
    """One verification probe against the named board. Returns metadata or None."""
    if ats == "greenhouse":
        return _try_greenhouse(slug)
    if ats == "lever":
        return _try_lever(slug)
    if ats == "ashby":
        return _try_ashby(slug)
    if ats == "workday":
        return _try_workday(careers_url)
    return None


def _display_name(ats: str, slug: str) -> str:
    """Readable fallback name for a URL-only add: 'acme-robotics' -> 'Acme Robotics'."""
    base = slug.split("/", 1)[0] if ats == "workday" else slug
    return re.sub(r"[-_]+", " ", base).strip().title()


def resolve_board_url(url: str, name: str = "") -> dict:
    """Turn a pasted careers link into a confirmed watchlist entry.

    Stores the exact token from the URL after one API probe. Raises
    UnsupportedBoardUrlError for hosts outside the supported set and
    BoardLookupError when a recognized link cannot be confirmed.
    """
    parsed = parse_board_url(url)
    if parsed is None:
        raise UnsupportedBoardUrlError(_SUPPORTED_BOARDS_MESSAGE)

    ats, slug = parsed["ats"], parsed["slug"]
    if ats == "greenhouse" and not slug:
        token = _greenhouse_token_from_page(url)
        if not token:
            raise BoardLookupError(
                "Could not find the Greenhouse board behind that link. "
                "Paste the boards.greenhouse.io link instead."
            )
        parsed = _greenhouse_board(token)
        slug = token
    if ats == "workday" and not slug:
        raise BoardLookupError(
            "Could not find the board name in that Workday link. "
            "Open a job on the careers page and paste that link."
        )

    probed = _probe_board(ats, slug, parsed.get("careers_url", ""))
    if probed is None:
        raise BoardLookupError("Could not confirm that job board. Check the link and try again.")

    return {"name": name.strip() or _display_name(ats, probed["slug"]), **probed}


# ---------------------------------------------------------------------------
# Evidence-first discovery: the user's own application rows
# ---------------------------------------------------------------------------

_EVIDENCE_URL_FILTERS = (
    "%greenhouse.io%",
    "%lever.co%",
    "%ashbyhq.com%",
    "%myworkdayjobs.com%",
)


def _applications_db_path() -> str:
    """Path to the applications DB, matching how the running backend sets it."""
    data_dir = os.getenv("JOB_FINDER_DATA_DIR")
    if data_dir:
        return os.path.join(data_dir, "job_tracker.db")
    try:
        from app.config import get_settings

        return get_settings().db_path
    except Exception:
        return os.path.join("data", "job_tracker.db")


def _evidence_from_applications(name: str) -> dict | None:
    """Find a proven board token in the user's own application rows.

    A stored job_url that parses to an ATS board token, on a row whose
    company matches ``name`` under the cross-source normalizer, is direct
    evidence: the board exists and this is its token. Read-only; any DB
    problem just returns None and discovery moves on.
    """
    from job_finder.dedup import companies_match, company_key

    target = company_key(name)
    if not target:
        return None
    db_path = _applications_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            where = " OR ".join(["job_url LIKE ?"] * len(_EVIDENCE_URL_FILTERS))
            rows = conn.execute(
                "SELECT company, job_url FROM applications "
                f"WHERE job_url IS NOT NULL AND ({where}) ORDER BY id DESC",
                _EVIDENCE_URL_FILTERS,
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        logger.debug("Could not read applications for board evidence", exc_info=True)
        return None

    for company, job_url in rows:
        if not companies_match(target, company_key(company or "")):
            continue
        parsed = parse_board_url(job_url or "")
        if parsed and parsed.get("slug"):
            return parsed
    return None


def discover_company(name: str) -> dict:
    """Auto-detect a company's ATS and board slug.

    Evidence from the user's own application rows wins first; slug
    guessing across Greenhouse, Lever, and Ashby is the last resort.
    Returns a dict with name, slug, ats, job_count, careers_url.
    """
    evidence = _evidence_from_applications(name)
    if evidence:
        probed = _probe_board(
            evidence["ats"], evidence["slug"], evidence.get("careers_url", "")
        )
        if probed:
            return {"name": name, **probed}
        # The probe is a nicety (job_count); the row already proved the token.
        return {
            "name": name,
            "slug": evidence["slug"],
            "ats": evidence["ats"],
            "job_count": 0,
            "careers_url": evidence.get("careers_url", ""),
        }

    slugs = _generate_slugs(name)
    if not slugs:
        return {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""}

    # Try each ATS in parallel for the most likely slug first, then expand
    ats_fns = [_try_greenhouse, _try_lever, _try_ashby]

    # Fast path: try the first slug on all ATS platforms simultaneously
    with ThreadPoolExecutor(max_workers=3) as pool:
        for slug in slugs[:3]:  # Try top 3 most likely slugs
            futures = {pool.submit(fn, slug): fn.__name__ for fn in ats_fns}
            for future in futures:
                result = future.result()
                if result:
                    return {"name": name, **result}

    # Slower path: try remaining slug variations
    for slug in slugs[3:]:
        for fn in ats_fns:
            result = fn(slug)
            if result:
                return {"name": name, **result}

    return {"name": name, "slug": slugs[0], "ats": "unknown", "job_count": 0, "careers_url": ""}


def build_watchlist_entries(company_names: list[str]) -> list[dict]:
    """Discover ATS-backed watchlist entries for a list of company names.

    First checks the curated company catalog (instant, no network) for
    known companies like Anthropic, Vercel, Supabase. Falls back to
    live ATS discovery (network probe) for unknown companies.

    Only confirmed ATS boards are returned. Unknown/unconfirmed companies are
    skipped so the scraper layer does not spray guessed slugs across every ATS.
    """
    from job_finder.config.company_catalog import lookup_company

    cleaned_names: list[str] = []
    seen: set[str] = set()
    for name in company_names:
        normalized = name.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_names.append(normalized)

    if not cleaned_names:
        return []

    results_by_name: dict[str, dict] = {}
    needs_discovery: list[str] = []

    # Phase 1: instant catalog lookup (no network)
    for name in cleaned_names:
        match = lookup_company(name)
        if match and match.get("ats") != "unknown" and match.get("slug"):
            results_by_name[name.lower()] = {
                "name": match["name"],
                "slug": match["slug"],
                "ats": match["ats"],
                "job_count": 0,
                "careers_url": "",
            }
        else:
            needs_discovery.append(name)

    # Phase 2: live ATS discovery for companies not in catalog
    if needs_discovery:
        workers = min(len(needs_discovery), 6)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(discover_company, name): name for name in needs_discovery}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                except Exception:
                    logger.debug("ATS discovery failed for %s", name, exc_info=True)
                    continue
                if not result:
                    continue
                if result.get("ats") == "unknown" or not result.get("slug"):
                    continue
                results_by_name[name.lower()] = result

    cataloged = len(results_by_name) - len([n for n in needs_discovery if n.lower() in results_by_name])
    if cataloged > 0:
        logger.info("Resolved %d/%d companies from catalog (no network), %d via live discovery",
                     cataloged, len(cleaned_names), len(results_by_name) - cataloged)

    return [results_by_name[name.lower()] for name in cleaned_names if name.lower() in results_by_name]


def _get_profile_path(profile: str) -> str:
    """Resolve the YAML file path for a profile."""
    config_dir = os.path.join(_PROJECT_ROOT, "src", "job_finder", "config", "profiles")
    name = profile if profile != "default" else "default"
    return os.path.join(config_dir, f"{name}.yaml")


def _load_profile_yaml(profile: str) -> dict:
    """Load profile YAML, falling back to template if needed."""
    path = _get_profile_path(profile)
    config_dir = os.path.dirname(path)
    template_path = os.path.join(config_dir, "_template.yaml")

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    elif os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_profile_yaml(profile: str, cfg: dict) -> None:
    """Write profile YAML back to disk."""
    path = _get_profile_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def get_watchlist(profile: str) -> dict:
    """Get the company watchlist for a profile."""
    cfg = _load_profile_yaml(profile)
    companies = cfg.get("watchlist", [])
    return {"profile": profile, "companies": companies}


_BOARD_HOST_HINTS = ("greenhouse.io/", "lever.co/", "ashbyhq.com/", "myworkdayjobs.com/")


def _looks_like_board_url(value: str) -> bool:
    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        return True
    return any(hint in lowered for hint in _BOARD_HOST_HINTS)


def add_company(profile: str, name: str, url: str = "") -> dict:
    """Add a company to the watchlist.

    With a careers ``url``, the exact board token from the link is stored
    after one verification probe (raises BoardUrlError when the link is
    unsupported or cannot be confirmed); an existing same-named entry is
    completed in place. With only a ``name``, ATS auto-discovery runs and
    a failed discovery is reported in the returned ``message`` so the
    caller can ask for the careers link.

    Returns the updated watchlist.
    """
    cfg = _load_profile_yaml(profile)
    watchlist = cfg.get("watchlist", [])

    name = (name or "").strip()
    url = (url or "").strip()
    if not url and _looks_like_board_url(name):
        # The user pasted a link into the name field; treat it as one.
        name, url = "", name

    message = ""
    if url:
        result = resolve_board_url(url, name=name)
    else:
        # Skip duplicates for name-only adds; a URL add may complete a row.
        normalized = name.lower()
        for entry in watchlist:
            if entry.get("name", "").lower() == normalized:
                return {"profile": profile, "companies": watchlist, "message": ""}
        logger.info("Discovering ATS for company: %s", name)
        result = discover_company(name)
        if result.get("ats") in ("", "unknown") or not result.get("slug"):
            result = {
                "name": result.get("name", name) or name,
                "slug": result.get("slug", ""),
                "ats": "unknown",
                "job_count": 0,
                "careers_url": "",
            }
            message = (
                f"Could not find a job board for {result['name']}. "
                "Paste its careers page link to finish setup."
            )

    normalized = result.get("name", "").strip().lower()
    replaced = False
    for i, entry in enumerate(watchlist):
        if entry.get("name", "").strip().lower() == normalized:
            watchlist[i] = result
            replaced = True
            break
    if not replaced:
        watchlist.append(result)

    cfg["watchlist"] = watchlist
    _save_profile_yaml(profile, cfg)

    return {"profile": profile, "companies": watchlist, "message": message}


def remove_company(profile: str, name: str) -> dict:
    """Remove a company from the watchlist."""
    cfg = _load_profile_yaml(profile)
    watchlist = cfg.get("watchlist", [])

    normalized = name.strip().lower()
    watchlist = [c for c in watchlist if c.get("name", "").lower() != normalized]

    cfg["watchlist"] = watchlist
    _save_profile_yaml(profile, cfg)

    return {"profile": profile, "companies": watchlist}
