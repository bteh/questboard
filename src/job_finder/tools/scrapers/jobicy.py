"""Jobicy — Remote jobs via public API (no auth required).

API docs: https://jobicy.com/api/v2/remote-jobs
Supports: count (max 50), tag, industry, geo filters.
"""

from __future__ import annotations

import logging
from typing import Any

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _strip_html

logger = logging.getLogger(__name__)

# Map common role keywords to Jobicy industry/tag filters.
# Without these, the API returns generic jobs (sales, marketing, etc.)
# and _match_roles filters them all out → "no results".
_ROLE_TO_INDUSTRIES: dict[str, str] = {
    "engineer": "engineering",
    "developer": "engineering",
    "devops": "engineering",
    "sre": "engineering",
    "software": "engineering",
    "backend": "engineering",
    "frontend": "engineering",
    "full stack": "engineering",
    "fullstack": "engineering",
    "data": "data-science",
    "machine learning": "data-science",
    "ml ": "data-science",
    "ai ": "data-science",
    "analyst": "data-science",
    "product": "product",
    "designer": "design",
    "ux": "design",
    "ui": "design",
    "marketing": "marketing",
    "sales": "sales",
    "finance": "finance",
    "hr ": "human-resources",
    "recruiter": "human-resources",
    "customer": "customer-support",
    "support": "customer-support",
    "writer": "copywriting",
    "content": "copywriting",
}


def _infer_industries(roles: list[str] | None) -> list[str]:
    """Map target roles to Jobicy industry filter values."""
    if not roles:
        return []
    industries: set[str] = set()
    for role in roles:
        role_lower = role.lower()
        for keyword, industry in _ROLE_TO_INDUSTRIES.items():
            if keyword in role_lower:
                industries.add(industry)
    return list(industries) or ["engineering"]  # default to engineering


@register_scraper(
    name="jobicy",
    display_name="Jobicy",
    url="https://jobicy.com",
    description="Remote jobs via public API",
    category="remote",
)
def search_jobicy(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch remote jobs from Jobicy's public API.

    Makes one request per inferred industry so that role-filtered results
    aren't empty (the API returns generic jobs without the industry param).
    """
    logger.info("Fetching jobs from Jobicy API...")

    industries = _infer_industries(roles)
    seen_urls: set[str] = set()
    results: list[dict] = []

    # Query each relevant industry (usually 1-2)
    for industry in industries:
        if len(results) >= max_results:
            break

        params: dict[str, Any] = {
            "count": 50,  # API max
            "industry": industry,
        }

        data = _get_json("https://jobicy.com/api/v2/remote-jobs", params=params)
        if not data or "jobs" not in data:
            continue

        for job in data["jobs"]:
            title = job.get("jobTitle", "")
            url = job.get("url", "")

            if url in seen_urls:
                continue
            seen_urls.add(url)

            if not _match_roles(title, roles):
                continue

            description = job.get("jobDescription", "")
            if description:
                description = _strip_html(description)

            sal_min = job.get("salaryMin") or job.get("annualSalaryMin")
            sal_max = job.get("salaryMax") or job.get("annualSalaryMax")

            results.append({
                "title": title,
                "company": job.get("companyName", ""),
                "location": job.get("jobGeo", "Remote"),
                "url": url,
                "source": "jobicy",
                "description": description[:3000],
                "salary_min": float(sal_min) if sal_min else None,
                "salary_max": float(sal_max) if sal_max else None,
                "date_posted": job.get("pubDate", ""),
                "is_remote": True,
                "company_size": "",
            })
            if len(results) >= max_results:
                break

    logger.info("Jobicy: found %d matching jobs", len(results))
    return results
