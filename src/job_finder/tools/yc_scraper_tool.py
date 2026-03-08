"""YC Work at a Startup scraper — returns normalized job dicts.

Scrapes https://www.workatastartup.com for engineering and leadership roles.
Returns the same dict format as ``search_jobs()`` so results can be merged
directly into the pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

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


def _try_parse_embedded_json(html: str) -> list[dict]:
    """Try to extract job data from embedded JSON in script tags.

    Many React/Next.js SPAs embed data in ``window.__NEXT_DATA__`` or
    similar global variables inside ``<script>`` tags.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    for script in soup.find_all("script"):
        text = script.string or ""

        # Try __NEXT_DATA__ (Next.js apps)
        if "__NEXT_DATA__" in text:
            try:
                match = re.search(r'__NEXT_DATA__\s*=\s*({.*?})\s*;?\s*$', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(1))
                    # Navigate the nested structure to find job listings
                    props = data.get("props", {}).get("pageProps", {})
                    job_list = props.get("jobs", props.get("jobListings", []))
                    for item in job_list:
                        jobs.append(_normalize_json_job(item))
            except (json.JSONDecodeError, AttributeError) as e:
                logger.debug("Failed to parse __NEXT_DATA__: %s", e)

        # Try other common patterns
        for pattern in [r'window\.JOBS\s*=\s*(\[.*?\]);', r'window\.jobs\s*=\s*(\[.*?\]);']:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    job_list = json.loads(match.group(1))
                    for item in job_list:
                        jobs.append(_normalize_json_job(item))
                except (json.JSONDecodeError, AttributeError):
                    pass

    return jobs


def _normalize_json_job(item: dict) -> dict:
    """Normalize a JSON job object from embedded data to our standard format."""
    # Handle various key naming conventions
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

    # Try to extract salary
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


def _parse_html_job_cards(html: str) -> list[dict]:
    """Parse job listing cards from HTML when embedded JSON is unavailable."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []

    # Try multiple selector strategies for robustness
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

    # Fallback: look for any links to /jobs/ paths
    if not cards:
        links = soup.select("a[href*='/jobs/']")
        for link in links:
            parent = link.find_parent("div") or link.find_parent("li")
            if parent and parent not in cards:
                cards.append(parent)

    for card in cards:
        # Extract title — try multiple patterns
        title_el = (
            card.select_one("h3, h4, [class*='title'], [class*='Title']")
            or card.select_one("a[href*='/jobs/']")
        )
        if not title_el:
            continue

        # Extract company
        company_el = card.select_one(
            "[class*='company'], [class*='Company'], [class*='org']"
        )
        company = company_el.get_text(strip=True) if company_el else ""

        # Extract location
        location_el = card.select_one(
            "[class*='location'], [class*='Location']"
        )
        location = location_el.get_text(strip=True) if location_el else ""

        # Extract link
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

    # Extract description
    desc_el = soup.select_one(
        "[class*='description'], [class*='job-description'], "
        "[class*='content'], article, .job-detail"
    )
    description = ""
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)[:3000]

    # Check for remote
    page_text = soup.get_text().lower()
    is_remote = "remote" in page_text[:2000]

    # Try to extract salary
    salary_match = re.search(
        r'\$(\d[\d,]+)\s*[-\u2013\u2014]\s*\$(\d[\d,]+)', soup.get_text()
    )
    salary_min = float(salary_match.group(1).replace(",", "")) if salary_match else None
    salary_max = float(salary_match.group(2).replace(",", "")) if salary_match else None

    # Detect ATS links (Greenhouse / Lever apply buttons)
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


def search_yc_jobs(
    roles: list[str] | None = None,
    max_results: int = 50,
    fetch_details: bool = True,
) -> list[dict]:
    """Scrape YC Work at a Startup for jobs matching target roles.

    Returns ``list[dict]`` in the same format as ``search_jobs()``.
    """
    url = f"{_BASE_URL}/jobs"
    logger.info("Fetching YC jobs from %s", url)

    html = _fetch_page(url)
    if not html:
        logger.warning("Could not fetch YC jobs page")
        return []

    # Strategy 1: Try embedded JSON (faster, more reliable)
    all_jobs = _try_parse_embedded_json(html)

    # Strategy 2: Fall back to HTML parsing
    if not all_jobs:
        all_jobs = _parse_html_job_cards(html)

    if not all_jobs:
        logger.warning("YC scraper found no jobs — page structure may have changed")
        return []

    # Filter by target roles if provided
    if roles:
        role_patterns = [r.lower() for r in roles]
        filtered = []
        for job in all_jobs:
            title_lower = job["title"].lower()
            # Match if any role pattern appears in the title
            if any(pattern in title_lower for pattern in role_patterns):
                filtered.append(job)
            # Also match broad engineering/data/leadership terms
            elif any(kw in title_lower for kw in [
                "data", "engineer", "director", "head of", "vp",
                "cto", "manager", "founding", "platform",
            ]):
                filtered.append(job)
        all_jobs = filtered

    # Limit results
    all_jobs = all_jobs[:max_results]

    # Optionally fetch detail pages for descriptions
    if fetch_details:
        for job in all_jobs:
            if job["url"] and not job["description"]:
                details = _fetch_job_detail(job["url"])
                job.update({k: v for k, v in details.items() if v})

    logger.info("YC scraper found %d jobs", len(all_jobs))
    return all_jobs
