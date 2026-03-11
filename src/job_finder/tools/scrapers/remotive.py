"""Remotive — Remote tech jobs via public API."""

from __future__ import annotations

import logging
from typing import Any

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _parse_salary, _strip_html

logger = logging.getLogger(__name__)


@register_scraper(
    name="remotive",
    display_name="Remotive",
    url="https://remotive.com",
    description="Remote tech jobs via public API",
    category="remote",
)
def search_remotive(
    roles: list[str] | None = None,
    max_results: int = 50,
    category: str | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch remote jobs from Remotive's public API."""
    logger.info("Fetching jobs from Remotive API...")

    params: dict[str, Any] = {"limit": max(max_results * 4, 300)}
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
