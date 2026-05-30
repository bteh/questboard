"""Greenhouse — Bulk company board scraper via JSON API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _clean_company_name,
    _get_json,
    _load_seed_slugs,
    _match_roles,
    _match_roles_crypto,
    _strip_html,
    is_crypto_company,
)

logger = logging.getLogger(__name__)

# Seeded from scrapers/data/greenhouse_seed.txt at import. Watchlist
# entries from the user's config are additive on top of this list.
_GREENHOUSE_COMPANIES: list[str] = _load_seed_slugs("greenhouse_seed.txt")


def _fetch_company_jobs(
    slug: str,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> list[dict]:
    """Fetch matching jobs for a single Greenhouse company board."""
    # Tight per-board timeout — see ashby.py for rationale. A single slow
    # board must not block the whole search.
    data = _get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        quiet_statuses={404},
        timeout=5,
    )
    if not data or "jobs" not in data:
        return []

    # Crypto/web3 companies use crypto-aware role matching (see ashby.py).
    crypto = is_crypto_company(slug)

    jobs: list[dict] = []
    for job in data["jobs"]:
        title = job.get("title", "")

        # Gate on the title BEFORE the costly HTML strip, so descriptions are
        # only parsed for postings that survive the role filter.
        if crypto:
            matched = _match_roles_crypto(
                title, roles, match_mode=match_mode,
                include_founding=include_founding,
            )
        else:
            matched = _match_roles(
                title, roles, match_mode=match_mode, include_founding=include_founding,
            )
        if not matched:
            continue

        loc = job.get("location", {})
        location = loc.get("name", "") if isinstance(loc, dict) else str(loc)

        # Extract description from HTML content
        content = job.get("content", "")
        description = _strip_html(content) if content else ""

        jobs.append({
            "title": title,
            "company": _clean_company_name(slug),
            "location": location,
            "url": job.get("absolute_url", ""),
            "source": "greenhouse",
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "date_posted": job.get("updated_at", ""),
            "is_remote": "remote" in location.lower(),
            "company_size": "",
            "crypto": crypto,
        })

    return jobs


@register_scraper(
    name="greenhouse",
    display_name="Greenhouse",
    url="https://greenhouse.io",
    description="Direct job listings from top company boards",
    category="ats",
)
def search_greenhouse(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
    watchlist_companies: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch jobs directly from Greenhouse boards API for known companies."""
    company_list = list(companies or _GREENHOUSE_COMPANIES)
    if watchlist_companies:
        company_list.extend(s for s in watchlist_companies if s not in company_list)
    if not company_list:
        logger.info("Greenhouse: no companies configured — add companies to your watchlist")
        return []
    logger.info("Fetching from Greenhouse API for %d companies...", len(company_list))

    results: list[dict] = []
    workers = min(len(company_list), 10)

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
                logger.warning("Greenhouse/%s failed: %s", slug, e)

    results = results[:max_results]
    logger.info("Greenhouse: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
