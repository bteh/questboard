"""BuiltIn — Startup and tech company job listings across 20+ categories.

Scrapes https://builtin.com/jobs search results pages. Server-side rendered
HTML with JSON-LD structured data. Supports all professions via keyword search
and 20 category filters (engineering, healthcare, marketing, finance, etc.).
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _match_roles, extract_salary_range

logger = logging.getLogger(__name__)

_BASE_URL = "https://builtin.com/jobs"

# BuiltIn's per-city pages live at ``/jobs/<slug>``. Their ``?location=``
# query param is treated as a soft hint and routinely returns unrelated
# cities (verified live: ``?location=Los Angeles`` returns mostly Toronto
# jobs). The path slug is the only filter that actually narrows by city.
# Cities not in this map fall back to the (best-effort) query param.
_CITY_SLUGS: dict[str, str] = {
    "los angeles": "los-angeles",
    "san francisco": "san-francisco",
    "san francisco bay area": "san-francisco",
    "sf": "san-francisco",
    "bay area": "san-francisco",
    "new york": "new-york",
    "new york city": "new-york",
    "nyc": "new-york",
    "boston": "boston",
    "seattle": "seattle",
    "austin": "austin",
    "chicago": "chicago",
    "washington dc": "washington-dc",
    "washington": "washington-dc",
    "dc": "washington-dc",
    "denver": "denver",
    "atlanta": "atlanta",
    "miami": "miami",
    "san diego": "san-diego",
    "dallas": "dallas",
    "houston": "houston",
    "philadelphia": "philadelphia",
    "portland": "portland",
    "minneapolis": "minneapolis",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 20
_PAGE_DELAY = 1.0  # seconds between page requests
_RESULTS_PER_PAGE = 25
_DIRECT_JOB_HOSTS = (
    "ashbyhq.com",
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "workable.com",
)
_AMBIGUOUS_LOCATION_RE = re.compile(
    r"^\s*(?:\d+\s+locations?|multiple\s+locations?)\s*$",
    re.IGNORECASE,
)
_COUNTRY_NAMES = {
    "US": "United States",
    "USA": "United States",
    "UNITED STATES OF AMERICA": "United States",
    "CA": "Canada",
    "CAN": "Canada",
}
_DETAIL_WORKERS = 8
_DETAIL_HYDRATION_LIMIT = 48


def _fuzzy_date_to_iso(prose: str) -> str:
    """Convert BuiltIn's age phrase to a real ISO date (UTC), or ''.

    'Reposted 20 Days Ago' -> today minus 20 days. The stored value must
    parse with _parse_posted_date so the pipeline's max_days_old freshness
    filter applies to builtin rows; callers keep date_confidence='fuzzy'
    because the day count is approximate.
    """
    if not prose:
        return ""
    text = prose.strip().lower()
    days: int | None = None
    if "today" in text or re.search(r"\bhours?\s+ago\b", text):
        days = 0
    elif "yesterday" in text:
        days = 1
    else:
        m = re.search(r"(\d+)\s+days?\s+ago", text)
        if m:
            days = int(m.group(1))
    if days is None:
        return ""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _fetch_page(url: str) -> str | None:
    """Fetch HTML page with error handling for Cloudflare."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 403:
            logger.warning("BuiltIn blocked request (Cloudflare): %s", url)
            return None
        resp.raise_for_status()
        # Detect Cloudflare challenge page
        if "challenge-platform" in resp.text[:2000] and "<title>Just a moment" in resp.text[:500]:
            logger.warning("BuiltIn served Cloudflare challenge page")
            return None
        return resp.text
    except requests.RequestException as e:
        logger.warning("BuiltIn fetch failed: %s", e)
        return None


def _parse_jsonld_jobs(html: str) -> list[dict]:
    """Extract job data from JSON-LD structured data if available."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        # Look for ItemList with ListItem entries
        if isinstance(data, dict) and data.get("@type") == "ItemList":
            for item in data.get("itemListElement", []):
                if isinstance(item, dict) and item.get("@type") == "ListItem":
                    jobs.append({
                        "name": item.get("name", ""),
                        "url": item.get("url", ""),
                    })
    return jobs


def _iter_job_postings(value):
    """Yield JobPosting objects from flat, list, or ``@graph`` JSON-LD."""
    if isinstance(value, dict):
        raw_type = value.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if "JobPosting" in types:
            yield value
        for child in value.get("@graph", []):
            yield from _iter_job_postings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_job_postings(child)


def _country_name(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("addressCountry") or ""
    raw = str(value or "").strip()
    return _COUNTRY_NAMES.get(raw.upper(), raw)


def _format_job_locations(posting: dict) -> str:
    """Recover concrete locations that Built In collapses to ``N Locations``."""
    raw_locations = posting.get("jobLocation") or []
    if isinstance(raw_locations, dict):
        raw_locations = [raw_locations]

    rendered: list[str] = []
    for raw in raw_locations if isinstance(raw_locations, list) else []:
        if not isinstance(raw, dict):
            continue
        address = raw.get("address") or {}
        if not isinstance(address, dict):
            continue
        city = str(address.get("addressLocality") or "").strip()
        region = str(address.get("addressRegion") or "").strip()
        country = _country_name(address.get("addressCountry"))
        label = ", ".join(part for part in (city, region, country) if part)
        if label and label not in rendered:
            rendered.append(label)

    # Fully remote postings sometimes omit jobLocation and publish only the
    # countries whose residents may apply. Keep that scope so a US seeker does
    # not inherit a Canada-only or Europe-only remote role.
    if not rendered:
        requirements = posting.get("applicantLocationRequirements") or []
        if isinstance(requirements, dict):
            requirements = [requirements]
        for raw in requirements if isinstance(requirements, list) else []:
            country = _country_name(raw)
            if country and country not in rendered:
                rendered.append(country)
    return "; ".join(rendered)


def _allowed_direct_url(value: object) -> str:
    url = str(value or "").strip()
    host = (urlparse(url).hostname or "").lower()
    if url.startswith("https://") and any(
        host == allowed or host.endswith(f".{allowed}")
        for allowed in _DIRECT_JOB_HOSTS
    ):
        return url
    return ""


def _embedded_application_url(html: str) -> str:
    """Read Built In's ``jobPostInit`` payload when no apply anchor exists."""
    match = re.search(
        r'"howToApply"\s*:\s*("(?:\\.|[^"\\])*")',
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    try:
        return _allowed_direct_url(json.loads(match.group(1)))
    except (json.JSONDecodeError, TypeError):
        return ""


def fetch_builtin_detail(url: str) -> dict:
    """Fetch one BuiltIn finalist and recover the detail card omitted by search.

    Search cards intentionally stay cheap and contain no description.  Agent
    matching needs requirements only for a few finalists, so hydrate lazily
    instead of adding dozens of detail requests to every source refresh.
    """

    if not url.startswith("https://builtin.com/job/"):
        return {}
    html = _fetch_page(url)
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div[id^='job-post-body-']")
    description = body.get_text("\n", strip=True) if body else ""
    description = "\n".join(
        line for line in (re.sub(r"\s+", " ", value).strip() for value in description.splitlines()) if line
    )

    date_posted = ""
    for value in soup.stripped_strings:
        text = re.sub(r"\s+", " ", value).strip()
        if re.fullmatch(
            r"(?:Posted|Reposted)\s+(?:Today|Yesterday|\d+\s+(?:Hours?|Days?)\s+Ago)",
            text,
            flags=re.IGNORECASE,
        ):
            date_posted = text
            break

    direct_url = ""
    for link in soup.find_all("a", href=True):
        direct_url = _allowed_direct_url(link.get("href"))
        if direct_url:
            break

    posting: dict = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        posting = next(_iter_job_postings(payload), {})
        if posting:
            break

    structured_date = str(posting.get("datePosted") or "").strip()
    structured_location = _format_job_locations(posting)
    location_type = str(posting.get("jobLocationType") or "").strip().lower()
    reported_remote = location_type in {"telecommute", "remote"}

    if not direct_url:
        direct_url = _embedded_application_url(html)

    posted_on = structured_date or _fuzzy_date_to_iso(date_posted)
    return {
        "description": description,
        "date_posted": posted_on,
        "date_confidence": (
            "exact" if structured_date else ("fuzzy" if posted_on else "missing")
        ),
        "direct_application_url": direct_url,
        "location": structured_location,
        "is_remote": reported_remote,
        "remote_flag_reported": reported_remote,
    }


def _hydrate_ambiguous_jobs(
    jobs: list[dict],
    *,
    limit: int = _DETAIL_HYDRATION_LIMIT,
) -> int:
    """Hydrate role-matched Built In rows whose card hides their locations.

    These are already cheap-card finalists: title, age, and role matching ran
    before this point. Fetching only the ambiguous subset recovers structured
    locations and official ATS URLs without paying one detail request for
    every Built In result.
    """
    candidates = [
        job for job in jobs
        if _AMBIGUOUS_LOCATION_RE.fullmatch(str(job.get("location") or ""))
        and str(job.get("url") or "").startswith("https://builtin.com/job/")
    ][:max(0, int(limit))]
    if not candidates:
        return 0

    hydrated = 0
    workers = min(_DETAIL_WORKERS, len(candidates))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_builtin_detail, str(job.get("url") or "")): job
            for job in candidates
        }
        for future in as_completed(futures):
            job = futures[future]
            try:
                detail = future.result()
            except Exception as exc:  # one bad detail must not cost the source
                logger.debug("BuiltIn detail hydration failed: %s", exc)
                continue
            if not detail:
                continue
            for field in (
                "description",
                "date_posted",
                "date_confidence",
                "direct_application_url",
                "location",
            ):
                if detail.get(field):
                    job[field] = detail[field]
            if detail.get("remote_flag_reported"):
                job["is_remote"] = bool(detail.get("is_remote"))
                job["remote_flag_reported"] = True
            hydrated += 1
    return hydrated


def _icon_sibling_text(card, icon_class: str) -> str:
    """Find the text next to a FontAwesome icon inside a card.

    BuiltIn nests icons inside a wrapper div; the label text lives in a
    sibling span or div one or two levels above the icon element.
    """
    icon = card.select_one(f"i[class*='{icon_class}']")
    if not icon:
        return ""
    # Walk up to two parent divs looking for a text-bearing sibling
    el = icon
    for _ in range(3):
        el = el.parent
        if not el:
            break
        for child in el.find_all(["span", "div"], recursive=False):
            if child.find("i"):
                continue  # skip the icon wrapper itself
            text = child.get_text(strip=True)
            if text:
                return text
    return ""


def _parse_html_jobs(
    html: str,
    roles: list[str] | None,
    max_results: int,
    *,
    max_days_old: int = 14,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> list[dict]:
    """Parse job cards from BuiltIn search results HTML."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # BuiltIn uses data-id="job-card" on each card container
    cards = soup.select("[data-id='job-card']")
    if not cards:
        # Fallback: find links to /job/ detail pages
        cards = []
        for link in soup.select("a[href*='/job/']"):
            parent = link.find_parent("div", class_=True)
            if parent and parent not in cards:
                cards.append(parent)

    for card in cards:
        if len(results) >= max_results:
            break

        # Title — data-id="job-card-title" or h2 a fallback
        title_el = card.select_one("[data-id='job-card-title'], h2 a, a[href*='/job/']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        if not _match_roles(title, roles, match_mode=match_mode, include_founding=include_founding):
            continue

        # URL
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            job_url = f"https://builtin.com{href}"
        else:
            job_url = href

        # Company — data-id="company-title" with <span> child
        company_el = card.select_one("[data-id='company-title']")
        if company_el:
            company = company_el.get_text(strip=True)
        else:
            # Fallback: image alt text (strip " Logo" suffix)
            img = card.select_one("img[alt]")
            company = re.sub(r"\s*Logo$", "", img.get("alt", "")).strip() if img else ""

        # Attributes are identified by their preceding FontAwesome icon:
        #   fa-house-building  → work type (Remote/In-Office/Hybrid)
        #   fa-location-dot    → location (city, state, country)
        #   fa-sack-dollar     → salary range
        #   fa-trophy          → experience level
        work_type = _icon_sibling_text(card, "fa-house-building")
        location = _icon_sibling_text(card, "fa-location-dot")
        salary_text = _icon_sibling_text(card, "fa-sack-dollar")
        # Period-aware extraction: '$50/hr' stays a raw 50.0 with
        # salary_period='hourly' instead of becoming 50000 via the old
        # x1000 heuristic in _parse_salary.
        salary = extract_salary_range(salary_text)

        is_remote = "remote" in work_type.lower() or "remote" in location.lower()

        # Date posted. Use a complete phrase: substring matching "ago" once
        # misclassified the company name "Dragos" as a posting date.
        date_posted = ""
        for span in card.select("span"):
            text = re.sub(r"\s+", " ", span.get_text(" ", strip=True)).strip()
            if re.fullmatch(
                r"(?:Posted|Reposted)?\s*(?:Today|Yesterday|\d+\s+(?:Hours?|Days?)\s+Ago)",
                text,
                flags=re.IGNORECASE,
            ):
                date_posted = text
                break

        age_match = re.search(r"(\d+)\s+Days?\s+Ago", date_posted, re.IGNORECASE)
        if age_match and int(age_match.group(1)) > max_days_old:
            continue

        # Store a REAL date, not the prose phrase — the pipeline freshness
        # filter parses date_posted, and 'Reposted 20 Days Ago' never parsed.
        posted_on = _fuzzy_date_to_iso(date_posted)

        loc_label = location or ("Remote" if is_remote else "Not specified")
        # Listing cards carry no description body. Synthesize a one-line
        # excerpt so downstream consumers (MCP rows, keyword scoring) never
        # see an empty description.
        excerpt_bits = [f"{title} at {company}" if company else title, loc_label]
        if work_type and work_type.lower() not in loc_label.lower():
            excerpt_bits.append(work_type)
        if salary_text:
            excerpt_bits.append(salary_text)
        description = " · ".join(bit for bit in excerpt_bits if bit)

        results.append({
            "title": title[:200],
            "company": company[:100],
            "location": loc_label,
            "url": job_url,
            "source": "builtin",
            "description": description,
            "salary_min": salary.salary_min,
            "salary_max": salary.salary_max,
            "salary_period": salary.period or "",
            "salary_currency": salary.currency or "",
            "date_posted": posted_on,
            "date_confidence": "fuzzy" if posted_on else "missing",
            "is_remote": is_remote,
            "company_size": "",
        })

    return results


def _build_search_url(
    roles: list[str] | None,
    locations: list[str] | None,
    page: int = 1,
    max_days_old: int = 14,
) -> str:
    """Build BuiltIn search URL from parameters.

    City filtering uses the path-slug form (``/jobs/los-angeles``) because
    BuiltIn's ``?location=`` query param is a soft hint that returns
    unrelated cities. See ``_CITY_SLUGS`` for the covered metros.
    """
    params: list[str] = []

    # Search term: use the first role as the keyword
    if roles:
        search_term = roles[0]
        params.append(f"search={requests.utils.quote(search_term)}")

    # Resolve location → either a path slug, a remote flag, or a
    # best-effort query-param fallback for unknown cities.
    path_slug: str | None = None
    if locations:
        # Pass 1: prefer a known city slug if any location has one.
        for loc in locations:
            city = loc.split(",")[0].strip().lower()
            slug = _CITY_SLUGS.get(city)
            if slug:
                path_slug = slug
                break
        if path_slug is None:
            # Pass 2: no known city — use remote flag or query fallback.
            for loc in locations:
                loc_lower = loc.lower().strip()
                if loc_lower in ("remote", "anywhere"):
                    params.append("working_option=2")
                    break
                city = loc.split(",")[0].strip()
                if city:
                    params.append(f"location={requests.utils.quote(city)}")
                    break

    # Days since posted
    if max_days_old <= 1:
        params.append("days_since_posted=1")
    elif max_days_old <= 3:
        params.append("days_since_posted=3")
    elif max_days_old <= 7:
        params.append("days_since_posted=7")
    else:
        params.append("days_since_posted=30")

    if page > 1:
        params.append(f"page={page}")

    base = f"{_BASE_URL}/{path_slug}" if path_slug else _BASE_URL
    query = "&".join(params)
    return f"{base}?{query}" if query else base


@register_scraper(
    name="builtin",
    display_name="BuiltIn",
    url="https://builtin.com",
    description="Tech jobs across 20+ hub cities, from startups to Netflix",
    # general, not startup: BuiltIn lists enterprises (Netflix, Disney,
    # GitLab). The startup category is a chip promise AND a company-tier
    # fallback signal, and this board keeps neither.
    category="general",
    enabled_by_default=True,
)
def search_builtin(
    roles: list[str] | None = None,
    max_results: int = 50,
    locations: list[str] | None = None,
    max_days_old: int = 14,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Scrape BuiltIn for jobs matching target roles.

    Fetches search result pages and parses job cards from HTML.
    Handles Cloudflare gracefully by returning empty on block.
    Works for any profession — engineering, healthcare, marketing, etc.
    """
    logger.info("Fetching jobs from BuiltIn...")
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    max_pages = max(1, (max_results + _RESULTS_PER_PAGE - 1) // _RESULTS_PER_PAGE)
    # Cap pages to avoid excessive requests
    max_pages = min(max_pages, 4)

    # Search with each role (up to 3) to get broader coverage
    search_roles = (roles or [None])[:3]

    for role in search_roles:
        if len(all_jobs) >= max_results:
            break
        role_list = [role] if role else None
        for page in range(1, max_pages + 1):
            if len(all_jobs) >= max_results:
                break

            url = _build_search_url(role_list, locations, page=page, max_days_old=max_days_old)
            html = _fetch_page(url)
            if not html:
                break  # Blocked or error — stop pagination

            jobs = _parse_html_jobs(
                html,
                roles,
                max_results - len(all_jobs),
                max_days_old=max_days_old,
                match_mode=match_mode,
                include_founding=include_founding,
            )
            if not jobs:
                break  # No more results

            for job in jobs:
                u = job.get("url", "")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    all_jobs.append(job)

            if page < max_pages:
                time.sleep(_PAGE_DELAY)

    detail_limit = kwargs.get("detail_hydration_limit", _DETAIL_HYDRATION_LIMIT)
    hydrated = _hydrate_ambiguous_jobs(all_jobs, limit=detail_limit)
    if hydrated:
        logger.info("BuiltIn: hydrated %d ambiguous multi-location jobs", hydrated)
    logger.info("BuiltIn: found %d matching jobs", len(all_jobs))
    return all_jobs[:max_results]
