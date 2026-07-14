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

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _match_roles, _parse_salary

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
        level = _icon_sibling_text(card, "fa-trophy")
        sal_min, sal_max = _parse_salary(salary_text)

        is_remote = "remote" in work_type.lower() or "remote" in location.lower()

        # The listing card carries no description body, so build a scannable one
        # from the stated facts rather than shipping an empty description.
        description = " · ".join(p for p in (work_type, location, salary_text, level) if p)

        # Date posted — first span with time-related text
        date_posted = ""
        for span in card.select("span"):
            text = span.get_text(strip=True)
            if any(w in text.lower() for w in ("ago", "posted", "today", "yesterday")):
                date_posted = text
                break

        results.append({
            "title": title[:200],
            "company": company[:100],
            "location": location or ("Remote" if is_remote else "Not specified"),
            "url": job_url,
            "source": "builtin",
            "description": description,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "date_posted": date_posted,
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
    description="Startup and growth-stage company jobs across 20+ categories",
    category="startup",
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

    logger.info("BuiltIn: found %d matching jobs", len(all_jobs))
    return all_jobs[:max_results]
