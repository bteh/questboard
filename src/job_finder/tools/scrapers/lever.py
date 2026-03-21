"""Lever — Bulk company postings scraper via JSON API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _clean_company_name,
    _get_json,
    _match_roles,
    _strip_html,
)

logger = logging.getLogger(__name__)

_LEVER_COMPANIES: list[str] = []  # Populated at runtime via watchlist + config


def _fetch_company_postings(slug: str, roles: list[str] | None) -> list[dict]:
    """Fetch matching postings for a single Lever company."""
    data = _get_json(f"https://api.lever.co/v0/postings/{slug}")
    if not data or not isinstance(data, list):
        return []

    results: list[dict] = []
    for posting in data:
        title = posting.get("text", "")
        if not _match_roles(title, roles):
            continue

        categories = posting.get("categories", {})
        location = categories.get("location", "")
        workplace = posting.get("workplaceType", "")

        desc_plain = posting.get("descriptionPlain", "")
        if not desc_plain:
            desc_plain = _strip_html(posting.get("description", ""))

        results.append({
            "title": title,
            "company": _clean_company_name(slug),
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

    return results


@register_scraper(
    name="lever",
    display_name="Lever",
    url="https://lever.co",
    description="Direct job postings from company career pages",
    category="ats",
)
def search_lever(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
    watchlist_companies: list[str] | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch jobs directly from Lever postings API for known companies."""
    company_list = list(companies or _LEVER_COMPANIES)
    if watchlist_companies:
        company_list.extend(s for s in watchlist_companies if s not in company_list)
    if not company_list:
        logger.info("Lever: no companies configured — add companies to your watchlist")
        return []
    logger.info("Fetching from Lever API for %d companies...", len(company_list))

    results: list[dict] = []
    workers = min(len(company_list), 8)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_company_postings, slug, roles): slug
            for slug in company_list
        }
        for future in as_completed(futures):
            try:
                jobs = future.result()
                results.extend(jobs)
            except Exception as e:
                slug = futures[future]
                logger.warning("Lever/%s failed: %s", slug, e)

    results = results[:max_results]
    logger.info("Lever: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
