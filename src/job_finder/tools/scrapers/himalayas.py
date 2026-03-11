"""Himalayas — Remote jobs with rich metadata via JSON API."""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _strip_html

logger = logging.getLogger(__name__)


@register_scraper(
    name="himalayas",
    display_name="Himalayas",
    url="https://himalayas.app",
    description="Remote jobs with rich company metadata",
    category="remote",
)
def search_himalayas(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch remote jobs from Himalayas API."""
    logger.info("Fetching jobs from Himalayas API...")

    results: list[dict] = []
    offset = 0
    page_size = 20  # API enforces max 20 per request

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
        if offset > 1000:
            break

    logger.info("Himalayas: found %d matching jobs", len(results))
    return results
