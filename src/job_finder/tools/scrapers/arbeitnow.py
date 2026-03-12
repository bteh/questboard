"""Arbeitnow — Remote and global jobs via public API (no auth required)."""

from __future__ import annotations

import logging
from typing import Any

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _parse_salary, _strip_html

logger = logging.getLogger(__name__)


@register_scraper(
    name="arbeitnow",
    display_name="Arbeitnow",
    url="https://www.arbeitnow.com",
    description="Remote and global jobs via public API",
    category="remote",
)
def search_arbeitnow(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch jobs from Arbeitnow's public job board API with pagination."""
    logger.info("Fetching jobs from Arbeitnow API...")

    results: list[dict] = []
    page = 1

    while len(results) < max_results:
        params: dict[str, Any] = {"page": page}
        data = _get_json(
            "https://www.arbeitnow.com/api/job-board-api",
            params=params,
        )
        if not data or "data" not in data:
            break

        jobs = data["data"]
        if not jobs:
            break

        for job in jobs:
            title = job.get("title", "")
            if not _match_roles(title, roles):
                continue

            tags = job.get("tags", []) or []
            description = job.get("description", "")
            if description:
                description = _strip_html(description)

            is_remote = bool(job.get("remote", False))

            # Extract salary from description text
            salary_min, salary_max = _parse_salary(description)

            results.append({
                "title": title,
                "company": job.get("company_name", ""),
                "location": job.get("location", "Remote" if is_remote else ""),
                "url": job.get("url", ""),
                "source": "arbeitnow",
                "description": description[:3000],
                "salary_min": salary_min,
                "salary_max": salary_max,
                "date_posted": job.get("created_at", ""),
                "is_remote": is_remote,
                "company_size": "",
            })
            if len(results) >= max_results:
                break

        # Check if there are more pages
        if not data.get("links", {}).get("next"):
            break
        page += 1
        if page > 20:
            break

    logger.info("Arbeitnow: found %d matching jobs", len(results))
    return results
