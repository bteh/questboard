"""YC Work at a Startup scraper — returns normalized job dicts.

Scrapes https://www.workatastartup.com for engineering and leadership roles.

The site uses Rails + Inertia.js, which embeds page data as JSON in a
``data-page`` attribute on the root ``<div id="app">``.  This is the
primary extraction strategy (most reliable).  Falls back to script-tag
JSON and HTML parsing if the page structure ever changes.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _match_roles

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.workatastartup.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_RATE_LIMIT_SECONDS = 2.0


def _fetch_page(url: str) -> str | None:
    """Fetch a URL with rate limiting and error handling."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        time.sleep(_RATE_LIMIT_SECONDS)
        return resp.text
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


# ── Strategy 1: Inertia.js data-page attribute (primary) ──


def _try_parse_inertia(html: str) -> list[dict]:
    """Extract job data from Inertia.js ``data-page`` attribute.

    WorkAtAStartup is a Rails + Inertia.js app.  Inertia embeds the full
    page props as JSON in ``<div id="app" data-page='{...}'>``.  The jobs
    live at ``props.jobs``.

    Uses regex + html.unescape for speed (avoids parsing the full page with
    BeautifulSoup).  Falls back to BS4 if the regex misses.
    """
    from html import unescape as html_unescape

    data = None

    # Fast path: regex extraction (avoids BS4 overhead on large pages)
    match = re.search(r'data-page="(.*?)"', html)
    if match:
        try:
            raw = html_unescape(match.group(1))
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            data = None

    # Fallback: BeautifulSoup (handles edge cases regex might miss)
    if data is None:
        soup = BeautifulSoup(html, "html.parser")
        app_div = soup.find("div", id="app")
        if not app_div:
            app_div = soup.find(attrs={"data-page": True})
        if not app_div:
            return []
        data_page = app_div.get("data-page", "")
        if not data_page:
            return []
        try:
            data = json.loads(data_page)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("Failed to parse Inertia data-page: %s", e)
            return []

    if not data:
        return []

    props = data.get("props", {})
    job_list = props.get("jobs", [])
    if not job_list:
        # Try alternative prop names
        job_list = props.get("jobListings", props.get("allJobs", []))

    jobs: list[dict] = []
    for item in job_list:
        if isinstance(item, dict):
            jobs.append(_normalize_json_job(item))

    if jobs:
        logger.info("YC: extracted %d jobs from Inertia.js data-page", len(jobs))
    return jobs


# ── Strategy 2: Script tag JSON (fallback for framework changes) ──


def _try_parse_embedded_json(html: str) -> list[dict]:
    """Try to extract job data from embedded JSON in script tags."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    for script in soup.find_all("script"):
        text = script.string or ""

        # Next.js apps
        if "__NEXT_DATA__" in text:
            try:
                match = re.search(r'__NEXT_DATA__\s*=\s*({.*?})\s*;?\s*$', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    props = data.get("props", {}).get("pageProps", {})
                    job_list = props.get("jobs", props.get("jobListings", []))
                    for item in job_list:
                        jobs.append(_normalize_json_job(item))
            except (json.JSONDecodeError, AttributeError) as e:
                logger.debug("Failed to parse __NEXT_DATA__: %s", e)

        # Direct window variable assignment
        for pattern in [
            r'window\.JOBS_GLOBALS\s*=\s*Object\.assign\(({.*?})\s*,',
            r'window\.JOBS\s*=\s*(\[.*?\]);',
            r'window\.jobs\s*=\s*(\[.*?\]);',
        ]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    raw = json.loads(match.group(1))
                    # JOBS_GLOBALS is metadata (filter options), not job data
                    if isinstance(raw, list):
                        for item in raw:
                            jobs.append(_normalize_json_job(item))
                except (json.JSONDecodeError, AttributeError):
                    pass

    # Also check for JSON-LD structured data (schema.org JobPosting)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "JobPosting":
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": item.get("hiringOrganization", {}).get("name", ""),
                        "location": item.get("jobLocation", {}).get("address", {}).get("addressLocality", ""),
                        "url": item.get("url", ""),
                        "source": "workatastartup",
                        "description": item.get("description", "")[:3000],
                        "salary_min": None,
                        "salary_max": None,
                        "date_posted": item.get("datePosted", ""),
                        "is_remote": "remote" in str(item.get("jobLocationType", "")).lower(),
                        "company_size": "",
                    })
        except (json.JSONDecodeError, AttributeError):
            pass

    return jobs


def _normalize_json_job(item: dict) -> dict:
    """Normalize a JSON job object from embedded data to our standard format."""
    company_name = (
        item.get("company_name", "")
        or item.get("companyName", "")
        or item.get("company", {}).get("name", "")
        if isinstance(item.get("company"), dict)
        else item.get("company", "")
    )

    location = item.get("location", "") or item.get("pretty_location", "")
    is_remote = bool(
        item.get("remote", False)
        or "remote" in str(location).lower()
    )

    job_url = item.get("url", "") or item.get("job_url", "")
    if job_url and not job_url.startswith("http"):
        job_url = f"{_BASE_URL}{job_url}"

    salary_min = item.get("salary_min") or item.get("salaryMin")
    salary_max = item.get("salary_max") or item.get("salaryMax")

    return {
        "title": item.get("title", "") or item.get("job_title", ""),
        "company": company_name if isinstance(company_name, str) else "",
        "location": location,
        "url": job_url,
        "source": "workatastartup",
        "description": item.get("description", "")[:3000],
        "salary_min": float(salary_min) if salary_min else None,
        "salary_max": float(salary_max) if salary_max else None,
        "date_posted": item.get("created_at", "") or item.get("posted_at", ""),
        "is_remote": is_remote,
        "company_size": item.get("team_size", "") or item.get("company_size", ""),
    }


# ── Strategy 3: HTML card parsing (last resort) ──


def _parse_html_job_cards(html: str) -> list[dict]:
    """Parse job listing cards from HTML when embedded JSON is unavailable."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    selectors = [
        "[class*='job-listing']",
        "[class*='JobListing']",
        "[class*='job_listing']",
        "div[class*='company-job']",
        "tr[class*='job']",
        ".directory-list .company-row",
    ]

    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    if not cards:
        links = soup.select("a[href*='/jobs/']")
        for link in links:
            parent = link.find_parent("div") or link.find_parent("li")
            if parent and parent not in cards:
                cards.append(parent)

    for card in cards:
        title_el = (
            card.select_one("h3, h4, [class*='title'], [class*='Title']")
            or card.select_one("a[href*='/jobs/']")
        )
        if not title_el:
            continue

        company_el = card.select_one(
            "[class*='company'], [class*='Company'], [class*='org']"
        )
        company = company_el.get_text(strip=True) if company_el else ""

        location_el = card.select_one(
            "[class*='location'], [class*='Location']"
        )
        location = location_el.get_text(strip=True) if location_el else ""

        link_el = card.select_one("a[href*='/jobs/']") or card.select_one("a[href]")
        job_url = ""
        if link_el:
            job_url = link_el.get("href", "")
            if job_url and not job_url.startswith("http"):
                job_url = f"{_BASE_URL}{job_url}"

        jobs.append({
            "title": title_el.get_text(strip=True),
            "company": company,
            "location": location,
            "url": job_url,
            "source": "workatastartup",
            "description": "",
            "salary_min": None,
            "salary_max": None,
            "date_posted": "",
            "is_remote": "remote" in location.lower(),
            "company_size": "",
        })

    return jobs


def _fetch_job_detail(job_url: str) -> dict:
    """Fetch additional details from a job's detail page."""
    html = _fetch_page(job_url)
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")

    desc_el = soup.select_one(
        "[class*='description'], [class*='job-description'], "
        "[class*='content'], article, .job-detail"
    )
    description = ""
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)[:3000]

    page_text = soup.get_text().lower()
    is_remote = "remote" in page_text[:2000]

    salary_match = re.search(
        r'\$(\d[\d,]+)\s*[-\u2013\u2014]\s*\$(\d[\d,]+)', soup.get_text()
    )
    salary_min = float(salary_match.group(1).replace(",", "")) if salary_match else None
    salary_max = float(salary_match.group(2).replace(",", "")) if salary_match else None

    ats_url = ""
    ats_type = ""
    apply_links = soup.select(
        "a[href*='greenhouse.io'], a[href*='lever.co'], "
        "a[href*='apply'], button[data-url]"
    )
    for link in apply_links:
        href = link.get("href", "") or link.get("data-url", "")
        if "greenhouse" in href:
            ats_url = href
            ats_type = "greenhouse"
            break
        elif "lever" in href:
            ats_url = href
            ats_type = "lever"
            break

    result: dict[str, Any] = {
        "description": description,
        "is_remote": is_remote,
    }
    if salary_min:
        result["salary_min"] = salary_min
    if salary_max:
        result["salary_max"] = salary_max
    if ats_url:
        result["ats_url"] = ats_url
        result["ats_type"] = ats_type

    return result


@register_scraper(
    name="workatastartup",
    display_name="YC Startups",
    url="https://workatastartup.com",
    description="YC Work at a Startup job listings",
    category="startup",
)
def search_yc_jobs(
    roles: list[str] | None = None,
    max_results: int = 50,
    fetch_details: bool = True,
    **kwargs,
) -> list[dict]:
    """Scrape YC Work at a Startup for jobs matching target roles.

    Extraction priority:
    1. Inertia.js ``data-page`` attribute (Rails + Inertia — current stack)
    2. Script-tag JSON (``__NEXT_DATA__``, ``window.JOBS``, JSON-LD)
    3. HTML card parsing (last resort)
    """
    url = f"{_BASE_URL}/jobs"
    logger.info("Fetching YC jobs from %s", url)

    html = _fetch_page(url)
    if not html:
        logger.warning("Could not fetch YC jobs page")
        return []

    # Try extraction strategies in order of reliability
    all_jobs = _try_parse_inertia(html)

    if not all_jobs:
        all_jobs = _try_parse_embedded_json(html)

    if not all_jobs:
        all_jobs = _parse_html_job_cards(html)

    if not all_jobs:
        logger.warning("YC scraper found no jobs — page structure may have changed")
        return []

    # Filter by target roles
    if roles:
        all_jobs = [j for j in all_jobs if _match_roles(j["title"], roles)]

    all_jobs = all_jobs[:max_results]

    if fetch_details:
        for job in all_jobs:
            if job["url"] and not job["description"]:
                details = _fetch_job_detail(job["url"])
                job.update({k: v for k, v in details.items() if v})

    logger.info("YC scraper found %d jobs", len(all_jobs))
    return all_jobs
