"""Workday ATS scraper — searches corporate career portals via public JSON API.

Many large employers (NVIDIA, Salesforce, Netflix, Adobe, etc.) run their
career sites on Workday. The Workday career site exposes a public JSON
search endpoint at ``/wday/cxs/{tenant}/{site_id}/jobs`` that requires no
authentication and returns structured job data including full descriptions.

This scraper searches multiple Workday-powered career portals in parallel,
filters by role keywords and location, and returns results in Launchboard's
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

logger = logging.getLogger(__name__)

_TIMEOUT = 20
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


# Built-in fallback if YAML is missing — US tech companies
_BUILTIN_EMPLOYERS: dict[str, dict] = {
    # Big Tech / FAANG+
    "nvidia": {
        "name": "NVIDIA",
        "tenant": "nvidia",
        "site_id": "NVIDIAExternalCareerSite",
        "base_url": "https://nvidia.wd5.myworkdayjobs.com",
    },
    "salesforce": {
        "name": "Salesforce",
        "tenant": "salesforce",
        "site_id": "External_Career_Site",
        "base_url": "https://salesforce.wd12.myworkdayjobs.com",
    },
    "netflix": {
        "name": "Netflix",
        "tenant": "netflix",
        "site_id": "Netflix",
        "base_url": "https://netflix.wd1.myworkdayjobs.com",
    },
    "adobe": {
        "name": "Adobe",
        "tenant": "adobe",
        "site_id": "external_experienced",
        "base_url": "https://adobe.wd5.myworkdayjobs.com",
    },
    "cisco": {
        "name": "Cisco",
        "tenant": "cisco",
        "site_id": "Cisco_Careers",
        "base_url": "https://cisco.wd5.myworkdayjobs.com",
    },
    "paypal": {
        "name": "PayPal",
        "tenant": "paypal",
        "site_id": "jobs",
        "base_url": "https://paypal.wd1.myworkdayjobs.com",
    },
    "intel": {
        "name": "Intel",
        "tenant": "intel",
        "site_id": "External",
        "base_url": "https://intel.wd1.myworkdayjobs.com",
    },
    "workday": {
        "name": "Workday",
        "tenant": "workday",
        "site_id": "Workday",
        "base_url": "https://workday.wd5.myworkdayjobs.com",
    },
    "mastercard": {
        "name": "Mastercard",
        "tenant": "mastercard",
        "site_id": "CorporateCareers",
        "base_url": "https://mastercard.wd1.myworkdayjobs.com",
    },
    # Tech / Enterprise
    "servicenow": {
        "name": "ServiceNow",
        "tenant": "servicenow",
        "site_id": "Careers",
        "base_url": "https://servicenow.wd1.myworkdayjobs.com",
    },
    "vmware": {
        "name": "VMware (Broadcom)",
        "tenant": "broadcom",
        "site_id": "Broadcom",
        "base_url": "https://broadcom.wd1.myworkdayjobs.com",
    },
    "uber": {
        "name": "Uber",
        "tenant": "uber",
        "site_id": "Uber_Careers",
        "base_url": "https://uber.wd5.myworkdayjobs.com",
    },
    "snap": {
        "name": "Snap",
        "tenant": "snap",
        "site_id": "Snap",
        "base_url": "https://snap.wd5.myworkdayjobs.com",
    },
    "target": {
        "name": "Target",
        "tenant": "target",
        "site_id": "TargetCareers",
        "base_url": "https://target.wd5.myworkdayjobs.com",
    },
    "capitalone": {
        "name": "Capital One",
        "tenant": "capitalone",
        "site_id": "Capital_One",
        "base_url": "https://capitalone.wd12.myworkdayjobs.com",
    },
    "jpmorgan": {
        "name": "JPMorgan Chase",
        "tenant": "jpmorgan",
        "site_id": "JPMorgan_Careers",
        "base_url": "https://jpmc.wd5.myworkdayjobs.com",
    },
    "visa": {
        "name": "Visa",
        "tenant": "visa",
        "site_id": "Visa_Careers",
        "base_url": "https://visa.wd12.myworkdayjobs.com",
    },
    "square": {
        "name": "Block (Square)",
        "tenant": "block",
        "site_id": "Block",
        "base_url": "https://block.wd1.myworkdayjobs.com",
    },
    "motorola": {
        "name": "Motorola Solutions",
        "tenant": "motorolasolutions",
        "site_id": "Careers",
        "base_url": "https://motorolasolutions.wd5.myworkdayjobs.com",
    },
    # Ride-hailing / Delivery / Marketplace
    "lyft": {
        "name": "Lyft",
        "tenant": "lyft",
        "site_id": "Lyft",
        "base_url": "https://lyft.wd5.myworkdayjobs.com",
    },
    "pinterest": {
        "name": "Pinterest",
        "tenant": "pinterestinc",
        "site_id": "PinterestCareers",
        "base_url": "https://pinterestinc.wd1.myworkdayjobs.com",
    },
    "instacart": {
        "name": "Instacart",
        "tenant": "instacart",
        "site_id": "Instacart",
        "base_url": "https://instacart.wd5.myworkdayjobs.com",
    },
    "doordash": {
        "name": "DoorDash",
        "tenant": "doordash",
        "site_id": "DoorDash",
        "base_url": "https://doordash.wd5.myworkdayjobs.com",
    },
    # Media / Entertainment
    "spotify": {
        "name": "Spotify",
        "tenant": "spotify",
        "site_id": "Spotify",
        "base_url": "https://spotify.wd5.myworkdayjobs.com",
    },
    # Banking / Finance — slug needs verification
    "goldmansachs": {
        "name": "Goldman Sachs",
        "tenant": "gsjobs",
        "site_id": "GOLDMANSACHSJOBS",
        "base_url": "https://gs.wd5.myworkdayjobs.com",
    },
}


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

def _api_search(employer: dict, query: str, limit: int = 20, offset: int = 0) -> dict | None:
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
            timeout=_TIMEOUT,
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


def _api_detail(employer: dict, external_path: str) -> dict | None:
    """GET full job detail from the Workday CXS endpoint."""
    url = f"{employer['base_url']}/wday/cxs/{employer['tenant']}/{employer['site_id']}{external_path}"
    try:
        resp = requests.get(
            url,
            headers={"Accept": "application/json", "User-Agent": _UA},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.debug("Workday detail fetch failed for %s: %s", external_path, e)
        return None


# ---------------------------------------------------------------------------
# Role matching
# ---------------------------------------------------------------------------

def _matches_roles(title: str, roles: list[str] | None) -> bool:
    """Check if a job title is relevant to the target roles."""
    if not roles:
        return True
    t = title.lower()
    for role in roles:
        if role.lower() in t:
            return True
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
) -> list[dict]:
    """Search a single Workday employer and return Launchboard job dicts."""
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
    seen_paths: set[str] = set()
    jobs: list[dict] = []

    for query in queries:
        if len(jobs) >= max_results:
            break

        data = _api_search(employer, query, limit=min(max_results, 20))
        if not data:
            continue

        for posting in data.get("jobPostings", []):
            path = posting.get("externalPath", "")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)

            title = posting.get("title", "")
            if not _matches_roles(title, roles):
                continue

            location = posting.get("locationsText", "")
            posted = posting.get("postedOn", "")

            # Build the public-facing URL
            job_url = f"{employer['base_url']}/{employer['site_id']}{path}"

            # Fetch full detail for description
            description = ""
            detail = _api_detail(employer, path)
            if detail:
                info = detail.get("jobPostingInfo", {})
                raw_desc = info.get("jobDescription", "")
                description = _html_to_text(raw_desc)

            is_remote = bool(
                re.search(r"remote|anywhere|work from home", location, re.IGNORECASE)
                or (detail and detail.get("jobPostingInfo", {}).get("remoteType"))
            )

            jobs.append({
                "title": title,
                "company": employer["name"],
                "location": location,
                "description": description[:5000],
                "url": job_url,
                "source": "workday",
                "is_remote": is_remote,
                "date_posted": posted,
                "salary_min": None,
                "salary_max": None,
                "company_size": "",
            })

            if len(jobs) >= max_results:
                break

    return jobs


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
    **kwargs,
) -> list[dict]:
    """Search all configured Workday employers in parallel.

    Each employer's career portal is queried via the public Workday CXS
    JSON API. Results include full job descriptions fetched from detail
    endpoints. No browser or authentication required.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    employers = _load_employers()
    if not employers:
        logger.warning("No Workday employers configured")
        return []

    per_employer = max(3, max_results // len(employers))
    all_jobs: list[dict] = []

    def _run(item: tuple[str, dict]) -> list[dict]:
        key, emp = item
        try:
            return _search_employer(key, emp, roles, per_employer)
        except Exception as e:
            logger.warning("Workday scraper failed for %s: %s", emp.get("name", key), e)
            return []

    workers = min(len(employers), 6)
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
    return all_jobs[:max_results]
