"""Wellfound (formerly AngelList) — Startup job listings.

Scrapes https://wellfound.com SEO landing pages by extracting embedded
Apollo state from ``__NEXT_DATA__`` script tags.  No auth required, but
the site uses DataDome anti-bot protection so requests may be blocked.
Falls back gracefully when that happens.
"""

from __future__ import annotations

import json
import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _match_roles, _parse_salary, _strip_html

logger = logging.getLogger(__name__)

_BASE_URL = "https://wellfound.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
_TIMEOUT = 20
_RATE_LIMIT = 3.0  # seconds between requests

# Map generic roles to Wellfound URL slugs
_ROLE_SLUGS = {
    "software engineer": "software-engineer",
    "backend engineer": "backend-developer",
    "frontend engineer": "frontend-developer",
    "full stack": "full-stack-developer",
    "data engineer": "data-engineer",
    "data scientist": "data-scientist",
    "machine learning": "machine-learning-engineer",
    "engineering manager": "engineering-manager",
    "product manager": "product-manager",
    "designer": "designer",
    "devops": "devops-engineer",
}

_LOCATION_SLUGS = {
    "remote": "remote",
    "san francisco": "san-francisco",
    "new york": "new-york",
    "los angeles": "los-angeles",
    "united states": "united-states",
}


def _fetch_page(url: str) -> str | None:
    """Fetch a URL with rate limiting and error handling."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 403:
            logger.warning("Wellfound blocked request (403): %s", url)
            return None
        resp.raise_for_status()
        time.sleep(_RATE_LIMIT)
        return resp.text
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def _extract_apollo_state(html: str) -> dict:
    """Extract Apollo state graph from __NEXT_DATA__ script tag."""
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}

    try:
        data = json.loads(script.string)
        # Apollo state lives at props.pageProps.apolloState.data
        return (
            data.get("props", {})
            .get("pageProps", {})
            .get("apolloState", {})
            .get("data", {})
        )
    except (json.JSONDecodeError, AttributeError) as e:
        logger.debug("Failed to parse __NEXT_DATA__: %s", e)
        return {}


def _resolve_ref(graph: dict, ref: dict | str | None) -> dict:
    """Resolve an Apollo cache reference like {__ref: 'Company:123'}."""
    if isinstance(ref, dict) and "__ref" in ref:
        return graph.get(ref["__ref"], {})
    if isinstance(ref, str) and ref in graph:
        return graph.get(ref, {})
    return {}


def _parse_jobs_from_graph(graph: dict, roles: list[str] | None, max_results: int) -> list[dict]:
    """Extract job listings from an Apollo state graph."""
    results: list[dict] = []

    for key, node in graph.items():
        # Job listing nodes typically have keys like "JobListing:123" or "StartupJobPosting:456"
        if not isinstance(node, dict):
            continue
        typename = node.get("__typename", "")
        if typename not in (
            "JobListing", "JobListingSearchResult", "StartupJobPosting",
            "JobPost", "Listing",
        ):
            # Also try matching by key prefix
            if not any(key.startswith(p) for p in ("JobListing:", "StartupJobPosting:", "JobPost:", "Listing:")):
                continue

        title = (
            node.get("title", "")
            or node.get("jobTitle", "")
            or node.get("name", "")
        )
        if not title:
            continue

        if not _match_roles(title, roles):
            continue

        # Resolve company reference
        company_ref = node.get("startup") or node.get("company") or node.get("organization")
        company_node = _resolve_ref(graph, company_ref) if company_ref else {}
        company_name = (
            company_node.get("name", "")
            or company_node.get("companyName", "")
            or node.get("companyName", "")
            or node.get("company_name", "")
            or ""
        )
        company_size = company_node.get("companySize", "") or company_node.get("size", "") or ""

        # Location
        location = node.get("locationNames", "") or node.get("location", "")
        if isinstance(location, list):
            location = ", ".join(location)
        remote = node.get("remote", False)
        if not location:
            location = "Remote" if remote else "Not specified"

        # Salary
        sal_min = node.get("compensation") or node.get("salary")
        if isinstance(sal_min, str):
            sal_min, sal_max = _parse_salary(sal_min)
        else:
            sal_min_val = node.get("salaryMin") or node.get("lowerBound") or node.get("compensationMin")
            sal_max_val = node.get("salaryMax") or node.get("upperBound") or node.get("compensationMax")
            sal_min = float(sal_min_val) if sal_min_val else None
            sal_max = float(sal_max_val) if sal_max_val else None

        # URL
        slug = node.get("slug", "") or node.get("jobSlug", "")
        company_slug = company_node.get("slug", "") or company_node.get("companySlug", "")
        job_url = node.get("url", "") or node.get("jobUrl", "")
        if not job_url and company_slug and slug:
            job_url = f"{_BASE_URL}/company/{company_slug}/jobs/{slug}"
        elif not job_url and slug:
            job_url = f"{_BASE_URL}/jobs/{slug}"

        # Description
        description = node.get("description", "") or node.get("descriptionHtml", "") or ""
        if "<" in description:
            description = _strip_html(description)

        results.append({
            "title": title,
            "company": company_name,
            "location": str(location),
            "url": job_url,
            "source": "wellfound",
            "description": description[:3000],
            "salary_min": sal_min,
            "salary_max": sal_max,
            "date_posted": node.get("liveStartAt", "") or node.get("postedAt", "") or node.get("createdAt", ""),
            "is_remote": bool(remote) or "remote" in str(location).lower(),
            "company_size": str(company_size),
        })

        if len(results) >= max_results:
            break

    return results


def _parse_html_fallback(html: str, roles: list[str] | None, max_results: int) -> list[dict]:
    """Fallback HTML parser when Apollo state is unavailable."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # Try common job card selectors
    selectors = [
        "[class*='styles_jobCard']",
        "[class*='styles_result']",
        "[data-test='JobListing']",
        "div[class*='jobListing']",
        "a[href*='/jobs/']",
    ]

    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    for card in cards:
        title_el = card.select_one("h2, h3, [class*='title'], [class*='Title']")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not _match_roles(title, roles):
            continue

        company_el = card.select_one("[class*='company'], [class*='Company'], [class*='startup']")
        company = company_el.get_text(strip=True) if company_el else ""

        location_el = card.select_one("[class*='location'], [class*='Location']")
        location = location_el.get_text(strip=True) if location_el else ""

        link_el = card if card.name == "a" else card.select_one("a[href]")
        job_url = ""
        if link_el:
            href = link_el.get("href", "")
            if href and not href.startswith("http"):
                job_url = f"{_BASE_URL}{href}"
            else:
                job_url = href

        salary_el = card.select_one("[class*='compensation'], [class*='salary']")
        sal_min, sal_max = _parse_salary(salary_el.get_text() if salary_el else "")

        results.append({
            "title": title,
            "company": company,
            "location": location or "Not specified",
            "url": job_url,
            "source": "wellfound",
            "description": "",
            "salary_min": sal_min,
            "salary_max": sal_max,
            "date_posted": "",
            "is_remote": "remote" in location.lower(),
            "company_size": "",
        })

        if len(results) >= max_results:
            break

    return results


def _build_urls(roles: list[str] | None) -> list[str]:
    """Build Wellfound SEO landing page URLs from target roles."""
    urls: list[str] = []

    if not roles:
        urls.append(f"{_BASE_URL}/role/l/software-engineer/remote")
        return urls

    for role in roles:
        role_lower = role.lower()
        # Find best matching slug
        slug = None
        for pattern, s in _ROLE_SLUGS.items():
            if pattern in role_lower:
                slug = s
                break

        if slug:
            urls.append(f"{_BASE_URL}/role/l/{slug}/remote")
        else:
            # Try the role as a slug directly
            slug = re.sub(r"[^a-z0-9]+", "-", role_lower).strip("-")
            urls.append(f"{_BASE_URL}/role/l/{slug}/remote")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


@register_scraper(
    name="wellfound",
    display_name="Wellfound",
    url="https://wellfound.com",
    description="Startup jobs from Wellfound (formerly AngelList) — may be blocked by anti-bot protection",
    category="startup",
    enabled_by_default=False,
)
def search_wellfound(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Scrape Wellfound for startup jobs matching target roles.

    Fetches SEO landing pages and extracts job data from embedded
    Apollo state (``__NEXT_DATA__``).  Falls back to HTML parsing
    if Apollo state is unavailable.  Returns empty list if blocked
    by DataDome anti-bot protection.
    """
    logger.info("Fetching jobs from Wellfound...")
    urls = _build_urls(roles)

    all_jobs: list[dict] = []
    seen_urls: set[str] = set()

    for url in urls:
        if len(all_jobs) >= max_results:
            break

        html = _fetch_page(url)
        if not html:
            continue

        # Strategy 1: Apollo state extraction
        graph = _extract_apollo_state(html)
        if graph:
            jobs = _parse_jobs_from_graph(graph, roles, max_results - len(all_jobs))
        else:
            # Strategy 2: HTML fallback
            jobs = _parse_html_fallback(html, roles, max_results - len(all_jobs))

        # Deduplicate
        for job in jobs:
            u = job.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                all_jobs.append(job)

    logger.info("Wellfound: found %d matching jobs", len(all_jobs))
    return all_jobs[:max_results]
