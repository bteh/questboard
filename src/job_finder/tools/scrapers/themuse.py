"""The Muse — Jobs via public API (free, API key optional)."""

from __future__ import annotations

import logging
from typing import Any

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _strip_html

logger = logging.getLogger(__name__)


@register_scraper(
    name="themuse",
    display_name="The Muse",
    url="https://www.themuse.com",
    description="Jobs with company culture profiles",
    category="general",
)
def search_themuse(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch jobs from The Muse's public API with pagination."""
    logger.info("Fetching jobs from The Muse API...")

    results: list[dict] = []
    page = 0

    while len(results) < max_results:
        params: dict[str, Any] = {
            "page": page,
        }

        data = _get_json(
            "https://www.themuse.com/api/public/jobs",
            params=params,
        )
        if not data or "results" not in data:
            break

        jobs = data["results"]
        if not jobs:
            break

        for job in jobs:
            title = job.get("name", "")
            if not _match_roles(title, roles):
                continue

            # Extract company name from nested object
            company_obj = job.get("company") or {}
            company = company_obj.get("name", "")

            # Extract locations from array of objects
            locations_list = job.get("locations") or []
            location = ", ".join(
                loc.get("name", "") for loc in locations_list if loc.get("name")
            )
            if not location:
                location = "Not specified"

            # Extract URL from refs
            refs = job.get("refs") or {}
            url = refs.get("landing_page", "")

            # Description is HTML — strip tags
            description = job.get("contents", "")
            if description:
                description = _strip_html(description)

            # Extract level from array of objects
            levels = job.get("levels") or []
            level_names = [lv.get("name", "") for lv in levels if lv.get("name")]

            # Determine remote status from location text
            location_lower = location.lower()
            is_remote = "remote" in location_lower or "flexible" in location_lower

            results.append({
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "source": "themuse",
                "description": description[:3000],
                "salary_min": None,
                "salary_max": None,
                "date_posted": job.get("publication_date", ""),
                "is_remote": is_remote,
                "company_size": "",
            })
            if len(results) >= max_results:
                break

        # Check if more pages exist
        page_count = data.get("page_count", 0)
        page += 1
        if page >= page_count:
            break
        if page > 20:
            break

    logger.info("The Muse: found %d matching jobs", len(results))
    return results
