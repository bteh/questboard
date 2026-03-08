"""Additional job board scrapers — Remotive, Himalayas, WWR, HN, Greenhouse, Lever.

Each function returns ``list[dict]`` in the same format as ``search_jobs()``:
    title, company, location, url, source, description,
    salary_min, salary_max, date_posted, is_remote, company_size
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from typing import Any

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, params: dict | None = None) -> dict | list | None:
    """GET a JSON endpoint with error handling."""
    try:
        resp = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None
    except ValueError as e:
        logger.warning("Invalid JSON from %s: %s", url, e)
        return None


def _parse_salary(text: str | None) -> tuple[float | None, float | None]:
    """Extract min/max salary from a text string like '$120,000 - $180,000'."""
    if not text:
        return None, None
    matches = re.findall(r'\$?([\d,]+(?:\.\d+)?)\s*[kK]?', text)
    if len(matches) >= 2:
        lo = float(matches[0].replace(",", ""))
        hi = float(matches[1].replace(",", ""))
        # If values look like they're in thousands (< 1000), multiply
        if lo < 1000:
            lo *= 1000
        if hi < 1000:
            hi *= 1000
        return lo, hi
    elif len(matches) == 1:
        val = float(matches[0].replace(",", ""))
        if val < 1000:
            val *= 1000
        return val, None
    return None, None


def _strip_html(html: str) -> str:
    """Crude HTML tag stripper for description fields."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:3000]


def _match_roles(title: str, roles: list[str] | None) -> bool:
    """Check if a job title matches any of the target roles (fuzzy)."""
    if not roles:
        return True
    title_lower = title.lower()
    for r in roles:
        if r.lower() in title_lower:
            return True
    # Broad engineering/data/leadership match
    broad = ["data", "engineer", "director", "head of", "vp ", "cto",
             "manager", "founding", "platform", "staff", "principal",
             "architect", "machine learning", "ml ", "ai "]
    return any(kw in title_lower for kw in broad)


# ===================================================================
# 1. REMOTIVE — Remote tech jobs (JSON API)
# ===================================================================

def search_remotive(
    roles: list[str] | None = None,
    max_results: int = 50,
    category: str | None = None,
) -> list[dict]:
    """Fetch remote jobs from Remotive's public API.

    API: GET https://remotive.com/api/remote-jobs
    Limit: ~4 requests/day on free tier.  Best used as a periodic fetch.
    """
    logger.info("Fetching jobs from Remotive API...")

    params: dict[str, Any] = {"limit": max(max_results * 3, 100)}
    if category:
        params["category"] = category

    data = _get_json("https://remotive.com/api/remote-jobs", params=params)
    if not data or "jobs" not in data:
        logger.warning("Remotive API returned no data")
        return []

    results: list[dict] = []
    for job in data["jobs"]:
        title = job.get("title", "")
        if not _match_roles(title, roles):
            continue

        sal_min, sal_max = _parse_salary(job.get("salary", ""))

        results.append({
            "title": title,
            "company": job.get("company_name", ""),
            "location": job.get("candidate_required_location", "Worldwide"),
            "url": job.get("url", ""),
            "source": "remotive",
            "description": _strip_html(job.get("description", ""))[:3000],
            "salary_min": sal_min,
            "salary_max": sal_max,
            "date_posted": job.get("publication_date", ""),
            "is_remote": True,
            "company_size": "",
        })
        if len(results) >= max_results:
            break

    logger.info("Remotive: found %d matching jobs", len(results))
    return results


# ===================================================================
# 2. HIMALAYAS — Remote jobs with rich metadata (JSON API)
# ===================================================================

def search_himalayas(
    roles: list[str] | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Fetch remote jobs from Himalayas API.

    API: GET https://himalayas.app/jobs/api?limit=N&offset=M
    Large dataset (100k+ jobs), no auth required.
    """
    logger.info("Fetching jobs from Himalayas API...")

    results: list[dict] = []
    offset = 0
    page_size = 50

    while len(results) < max_results:
        data = _get_json(
            "https://himalayas.app/jobs/api",
            params={"limit": page_size, "offset": offset},
        )
        if not data or "jobs" not in data:
            break

        jobs = data["jobs"]
        if not jobs:
            break

        for job in jobs:
            title = job.get("title", "")
            if not _match_roles(title, roles):
                continue

            sal_min = job.get("minSalary")
            sal_max = job.get("maxSalary")

            # Location from restrictions or "Remote"
            loc_list = job.get("locationRestrictions") or []
            location = ", ".join(loc_list) if loc_list else "Remote"

            results.append({
                "title": title,
                "company": job.get("companyName", ""),
                "location": location,
                "url": job.get("applicationLink", ""),
                "source": "himalayas",
                "description": _strip_html(job.get("description", ""))[:3000],
                "salary_min": float(sal_min) if sal_min else None,
                "salary_max": float(sal_max) if sal_max else None,
                "date_posted": job.get("pubDate", ""),
                "is_remote": True,
                "company_size": "",
            })
            if len(results) >= max_results:
                break

        offset += page_size
        # Safety: don't paginate forever
        if offset > 500:
            break

    logger.info("Himalayas: found %d matching jobs", len(results))
    return results


# ===================================================================
# 3. WE WORK REMOTELY — Remote jobs via RSS feed
# ===================================================================

_WWR_CATEGORIES = {
    "programming": "remote-programming-jobs",
    "data": "remote-programming-jobs",
    "devops": "remote-devops-sysadmin-jobs",
    "management": "remote-management-finance-jobs",
    "all": "remote-jobs",
}


def search_weworkremotely(
    roles: list[str] | None = None,
    max_results: int = 50,
    categories: list[str] | None = None,
) -> list[dict]:
    """Fetch remote jobs from We Work Remotely RSS feeds.

    RSS: GET https://weworkremotely.com/categories/{cat}.rss
    """
    logger.info("Fetching jobs from We Work Remotely RSS...")

    cats = categories or ["programming", "devops"]
    all_items: list[dict] = []

    for cat in cats:
        slug = _WWR_CATEGORIES.get(cat, cat)
        url = f"https://weworkremotely.com/categories/{slug}.rss"
        try:
            resp = requests.get(url, headers={
                "User-Agent": _HEADERS["User-Agent"],
                "Accept": "application/rss+xml,application/xml,text/xml",
            }, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("WWR RSS fetch failed for %s: %s", cat, e)
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning("WWR RSS parse failed for %s: %s", cat, e)
            continue

        for item in root.iter("item"):
            raw_title = item.findtext("title", "")
            # WWR title format: "Company: Job Title (Location)"
            parts = raw_title.split(":", 1)
            if len(parts) == 2:
                company = parts[0].strip()
                title = parts[1].strip()
            else:
                company = ""
                title = raw_title

            # Strip trailing location in parens
            loc_match = re.search(r"\(([^)]+)\)\s*$", title)
            region = item.findtext("region", "")
            if loc_match:
                region = loc_match.group(1)
                title = title[: loc_match.start()].strip()

            if not _match_roles(title, roles):
                continue

            desc_html = item.findtext("description", "")
            description = _strip_html(desc_html)

            all_items.append({
                "title": title,
                "company": company,
                "location": region or "Remote",
                "url": item.findtext("link", ""),
                "source": "weworkremotely",
                "description": description,
                "salary_min": None,
                "salary_max": None,
                "date_posted": item.findtext("pubDate", ""),
                "is_remote": True,
                "company_size": "",
            })

    # Deduplicate by URL
    seen: set[str] = set()
    results: list[dict] = []
    for job in all_items:
        u = job["url"]
        if u and u not in seen:
            seen.add(u)
            results.append(job)
        if len(results) >= max_results:
            break

    logger.info("We Work Remotely: found %d matching jobs", len(results))
    return results


# ===================================================================
# 4. HACKER NEWS "Who is Hiring?" — Algolia API
# ===================================================================

def search_hn_hiring(
    roles: list[str] | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Fetch jobs from the latest HN 'Who is hiring?' thread.

    Uses Algolia's HN Search API to find the thread, then fetches comments.
    Each top-level comment is a job posting by a hiring company.
    """
    logger.info("Fetching HN 'Who is Hiring?' thread...")

    # Step 1: Find the latest thread
    now = datetime.now(timezone.utc)
    current_month = now.strftime("%B %Y")
    prev_month = (now.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%B %Y")

    thread_id = None
    for query_month in [current_month, prev_month]:
        search_url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": f"Ask HN: Who is hiring? ({query_month})",
            "tags": "ask_hn",
            "hitsPerPage": 3,
        }
        data = _get_json(search_url, params=params)
        if data and data.get("hits"):
            for hit in data["hits"]:
                title = hit.get("title", "")
                if "who is hiring" in title.lower() and query_month.split()[0].lower() in title.lower():
                    thread_id = hit.get("objectID")
                    break
        if thread_id:
            break

    if not thread_id:
        # Fallback: get the most recent "who is hiring" thread
        data = _get_json(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": "Who is hiring",
                "tags": "ask_hn",
                "hitsPerPage": 5,
            },
        )
        if data and data.get("hits"):
            for hit in data["hits"]:
                if "who is hiring" in hit.get("title", "").lower():
                    thread_id = hit["objectID"]
                    break

    if not thread_id:
        logger.warning("Could not find HN 'Who is Hiring?' thread")
        return []

    logger.info("Found HN thread ID: %s", thread_id)

    # Step 2: Fetch the thread and its comments
    thread_data = _get_json(f"https://hn.algolia.com/api/v1/items/{thread_id}")
    if not thread_data or "children" not in thread_data:
        logger.warning("Could not fetch HN thread comments")
        return []

    results: list[dict] = []
    for comment in thread_data["children"]:
        text = comment.get("text", "")
        if not text:
            continue

        # Parse the comment — HN hiring posts usually start with:
        # "Company Name | Role | Location | Remote | Salary"
        plain = _strip_html(text)
        first_line = plain.split("\n")[0] if "\n" in plain else plain[:200]

        # Try to extract company from first line using pipe separator
        pipe_parts = [p.strip() for p in first_line.split("|")]
        if len(pipe_parts) >= 2:
            company = pipe_parts[0]
            # Look for a role-like part
            title = ""
            location = ""
            is_remote = False
            for part in pipe_parts[1:]:
                pl = part.lower()
                if any(kw in pl for kw in ["remote", "onsite", "hybrid"]):
                    is_remote = "remote" in pl
                    if not location:
                        location = part
                elif any(kw in pl for kw in [
                    "engineer", "developer", "data", "manager", "director",
                    "designer", "lead", "head", "vp", "cto", "founding",
                    "hiring", "multiple", "senior", "staff", "principal",
                ]):
                    if not title:
                        title = part
                elif re.match(r"^[A-Z][a-z]", part) and len(part) < 50:
                    if not location:
                        location = part

            if not title:
                title = pipe_parts[1] if len(pipe_parts) > 1 else company

            if not _match_roles(title, roles):
                continue

            # Try to find a URL in the comment
            url_match = re.search(r'https?://[^\s<"]+', text)
            job_url = url_match.group(0) if url_match else ""

            results.append({
                "title": title[:200],
                "company": company[:100],
                "location": location or "Not specified",
                "url": job_url,
                "source": "hackernews",
                "description": plain[:3000],
                "salary_min": None,
                "salary_max": None,
                "date_posted": comment.get("created_at", ""),
                "is_remote": is_remote,
                "company_size": "",
            })

            if len(results) >= max_results:
                break

    logger.info("HN Who is Hiring: found %d matching jobs", len(results))
    return results


# ===================================================================
# 5. GREENHOUSE — Bulk company board scraper (JSON API)
# ===================================================================

# Top companies known to use Greenhouse
_GREENHOUSE_COMPANIES = [
    "anthropic", "openai", "stripe", "databricks", "figma",
    "notion", "airbnb", "cloudflare", "coinbase", "plaid",
    "ramp", "scale", "brex", "gusto", "dbt-labs",
    "duolingo", "instacart", "pinterest", "affirm", "hashicorp",
    "anduril", "palantir", "sqsp", "hubspot", "gitlab",
    "nerdwallet", "docusign", "grammarly", "rivian", "airtable",
]


def search_greenhouse(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs directly from Greenhouse boards API for known companies.

    API: GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
    No auth required. Returns all public listings for a company.
    """
    company_list = companies or _GREENHOUSE_COMPANIES
    logger.info("Fetching from Greenhouse API for %d companies...", len(company_list))

    results: list[dict] = []
    for slug in company_list:
        if len(results) >= max_results:
            break

        data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        if not data or "jobs" not in data:
            continue

        for job in data["jobs"]:
            title = job.get("title", "")
            if not _match_roles(title, roles):
                continue

            loc = job.get("location", {})
            location = loc.get("name", "") if isinstance(loc, dict) else str(loc)

            results.append({
                "title": title,
                "company": slug.replace("-", " ").title(),
                "location": location,
                "url": job.get("absolute_url", ""),
                "source": "greenhouse",
                "description": "",  # Greenhouse list endpoint doesn't include descriptions
                "salary_min": None,
                "salary_max": None,
                "date_posted": job.get("updated_at", ""),
                "is_remote": "remote" in location.lower(),
                "company_size": "",
            })

            if len(results) >= max_results:
                break

        # Small delay to be respectful
        time.sleep(0.3)

    logger.info("Greenhouse: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results


# ===================================================================
# 6. LEVER — Bulk company postings scraper (JSON API)
# ===================================================================

# Companies known to use Lever (verified working slugs)
_LEVER_COMPANIES = [
    "plaid", "mistral", "anyscale",
]


def search_lever(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs directly from Lever postings API for known companies.

    API: GET https://api.lever.co/v0/postings/{slug}
    No auth required. Returns 404 for companies not using Lever.
    """
    company_list = companies or _LEVER_COMPANIES
    logger.info("Fetching from Lever API for %d companies...", len(company_list))

    results: list[dict] = []
    for slug in company_list:
        if len(results) >= max_results:
            break

        data = _get_json(f"https://api.lever.co/v0/postings/{slug}")
        if not data or not isinstance(data, list):
            continue

        for posting in data:
            title = posting.get("text", "")
            if not _match_roles(title, roles):
                continue

            categories = posting.get("categories", {})
            location = categories.get("location", "")
            workplace = posting.get("workplaceType", "")

            # Extract description
            desc_plain = posting.get("descriptionPlain", "")
            if not desc_plain:
                desc_plain = _strip_html(posting.get("description", ""))

            results.append({
                "title": title,
                "company": slug.replace("-", " ").title(),
                "location": location,
                "url": posting.get("hostedUrl", ""),
                "source": "lever",
                "description": desc_plain[:3000],
                "salary_min": None,
                "salary_max": None,
                "date_posted": "",
                "is_remote": workplace == "remote" or "remote" in location.lower(),
                "company_size": "",
            })

            if len(results) >= max_results:
                break

        time.sleep(0.3)

    logger.info("Lever: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results


# ===================================================================
# Unified entry point
# ===================================================================

def search_additional_sources(
    roles: list[str] | None = None,
    max_results_per_source: int = 25,
    sources: list[str] | None = None,
    progress: Any = None,
) -> list[dict]:
    """Run all (or selected) additional scrapers and merge results.

    Parameters
    ----------
    roles : target role keywords for filtering
    max_results_per_source : cap per individual source
    sources : list of source names to run, or None for all
    progress : optional callback ``fn(msg: str)``
    """
    available = {
        "remotive": search_remotive,
        "himalayas": search_himalayas,
        "weworkremotely": search_weworkremotely,
        "hackernews": search_hn_hiring,
        "greenhouse": search_greenhouse,
        "lever": search_lever,
    }

    active = sources or list(available.keys())
    all_jobs: list[dict] = []

    for name in active:
        fn = available.get(name)
        if not fn:
            logger.warning("Unknown source: %s", name)
            continue
        try:
            if progress:
                progress(f"Searching {name}...")
            jobs = fn(roles=roles, max_results=max_results_per_source)
            all_jobs.extend(jobs)
            if progress:
                progress(f"  Found {len(jobs)} jobs from {name}")
        except Exception as e:
            logger.warning("Scraper %s failed (non-fatal): %s", name, e)
            if progress:
                progress(f"  {name} unavailable: {e}")

    return all_jobs
