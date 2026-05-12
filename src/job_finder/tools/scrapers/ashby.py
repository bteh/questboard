"""Ashby — Company career page scraper via public job board API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _clean_company_name,
    _get_json,
    _load_seed_slugs,
    _match_roles,
)

logger = logging.getLogger(__name__)

# Seeded from scrapers/data/ashby_seed.txt at import. Ashby is the newer ATS
# preferred by AI-native and modern dev-tool startups — high-signal coverage
# for the Series A–C cohort. Watchlist entries are additive.
_ASHBY_COMPANIES: list[str] = _load_seed_slugs("ashby_seed.txt")


def _fetch_company_jobs(
    slug: str,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> list[dict]:
    """Fetch matching jobs for a single Ashby company board."""
    # Tight per-board timeout: with 100+ seeded + discovered companies, a
    # 15s default would let a single slow board stall the worker pool for
    # 15s — multiply by dozens of unreachable boards and the whole search
    # ends up minutes behind. 5s is plenty for a healthy Ashby endpoint
    # (typical response is <1s).
    data = _get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
        quiet_statuses={404},
        timeout=5,
    )
    if not data or "jobs" not in data:
        return []

    jobs: list[dict] = []
    for job in data["jobs"]:
        title = job.get("title", "")
        if not _match_roles(title, roles, match_mode=match_mode, include_founding=include_founding):
            continue

        location = job.get("location", "")
        is_remote = job.get("isRemote", False) or job.get("workplaceType", "").lower() == "remote"

        # Parse compensation
        salary_min = None
        salary_max = None
        comp = job.get("compensation")
        if comp and isinstance(comp, dict):
            tiers = comp.get("compensationTiers", [])
            if tiers:
                components = tiers[0].get("components", [])
                for c in components:
                    if c.get("compensationType") == "Salary":
                        salary_min = c.get("minValue")
                        salary_max = c.get("maxValue")
                        break

        jobs.append({
            "title": title,
            "company": _clean_company_name(slug),
            "location": location,
            "url": job.get("jobUrl", ""),
            "source": "ashby",
            "description": (job.get("descriptionPlain", "") or "")[:3000],
            "salary_min": salary_min,
            "salary_max": salary_max,
            "date_posted": job.get("publishedAt", ""),
            "is_remote": is_remote,
            "company_size": "",
        })

    return jobs


@register_scraper(
    name="ashby",
    display_name="Ashby",
    url="https://ashbyhq.com",
    description="Direct job postings from Ashby career pages",
    category="ats",
)
def search_ashby(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
    watchlist_companies: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch jobs directly from Ashby job board API for specified companies."""
    company_list = list(companies or _ASHBY_COMPANIES)
    if watchlist_companies:
        company_list.extend(s for s in watchlist_companies if s not in company_list)
    if not company_list:
        return []

    logger.info("Fetching from Ashby API for %d companies...", len(company_list))

    results: list[dict] = []
    workers = min(len(company_list), 8)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _fetch_company_jobs, slug, roles,
                match_mode=match_mode, include_founding=include_founding,
            ): slug
            for slug in company_list
        }
        for future in as_completed(futures):
            try:
                jobs = future.result()
                results.extend(jobs)
            except Exception as e:
                slug = futures[future]
                logger.debug("Ashby/%s failed: %s", slug, e)

    results = results[:max_results]
    logger.info("Ashby: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
