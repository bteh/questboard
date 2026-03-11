"""RemoteOK — Remote-first jobs via free JSON API."""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _strip_html

logger = logging.getLogger(__name__)


@register_scraper(
    name="remoteok",
    display_name="RemoteOK",
    url="https://remoteok.com",
    description="Remote-first job listings",
    category="remote",
)
def search_remoteok(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch remote jobs from RemoteOK's public JSON API."""
    logger.info("Fetching jobs from RemoteOK API...")

    data = _get_json("https://remoteok.com/api")
    if not data or not isinstance(data, list):
        logger.warning("RemoteOK API returned no data")
        return []

    results: list[dict] = []
    # First element is a legal/attribution notice — skip it
    for item in data[1:]:
        if not isinstance(item, dict):
            continue

        title = item.get("position", "")
        if not title or not _match_roles(title, roles):
            continue

        sal_min, sal_max = None, None
        if item.get("salary_min"):
            try:
                sal_min = float(item["salary_min"])
            except (ValueError, TypeError):
                pass
        if item.get("salary_max"):
            try:
                sal_max = float(item["salary_max"])
            except (ValueError, TypeError):
                pass

        tags = item.get("tags", [])
        desc = item.get("description", "")
        if tags:
            desc = f"Skills: {', '.join(tags)}\n\n{desc}"

        location = item.get("location", "Remote")
        company = item.get("company", "")
        slug = item.get("slug", "")
        url = item.get("url", f"https://remoteok.com/remote-jobs/{slug}" if slug else "")

        results.append({
            "title": title,
            "company": company,
            "location": location or "Remote",
            "url": url,
            "source": "remoteok",
            "description": _strip_html(desc)[:3000],
            "salary_min": sal_min,
            "salary_max": sal_max,
            "date_posted": item.get("date", ""),
            "is_remote": True,
            "company_size": "",
        })
        if len(results) >= max_results:
            break

    logger.info("RemoteOK: found %d matching jobs", len(results))
    return results
