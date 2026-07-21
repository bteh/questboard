"""Lever — Bulk company postings scraper via JSON API."""

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
    rank_by_relevance,
    _strip_html,
    date_confidence_for,
    is_crypto_company,
)

logger = logging.getLogger(__name__)

# Seeded from scrapers/data/lever_seed.txt at import. Watchlist entries from
# the user's config are additive on top of this list.
_LEVER_COMPANIES: list[str] = _load_seed_slugs("lever_seed.txt")


def _fetch_company_postings(
    slug: str,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> list[dict]:
    """Fetch matching postings for a single Lever company."""
    # Tight per-board timeout — see ashby.py for rationale.
    data = _get_json(
        f"https://api.lever.co/v0/postings/{slug}",
        quiet_statuses={404},
        timeout=5,
    )
    if not data or not isinstance(data, list):
        return []

    # Crypto/web3 companies use crypto-aware role matching (see ashby.py).
    crypto = is_crypto_company(slug)

    results: list[dict] = []
    for posting in data:
        title = posting.get("text", "")

        # Gate on the title BEFORE building the (possibly HTML-stripped)
        # description, so it's only computed for postings that pass the filter.
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

        categories = posting.get("categories", {})
        location = categories.get("location", "")
        workplace = posting.get("workplaceType", "")

        desc_plain = posting.get("descriptionPlain", "")
        if not desc_plain:
            desc_plain = _strip_html(posting.get("description", ""))
        desc_plain = desc_plain[:3000]

        # Lever's postings API returns createdAt as epoch ms — the pipeline's
        # _parse_posted_date handles it, so stale jobs no longer bypass the
        # freshness filter via a hardcoded empty date.
        created_at = posting.get("createdAt", "")

        results.append({
            "title": title,
            "company": _clean_company_name(slug),
            "location": location,
            "url": posting.get("hostedUrl", ""),
            "source": "lever",
            "description": desc_plain,
            "salary_min": None,
            "salary_max": None,
            "date_posted": created_at,
            "date_confidence": date_confidence_for(created_at),
            "is_remote": workplace == "remote" or "remote" in location.lower(),
            # workplaceType is a definitive ATS flag; 'remote' appearing in
            # free-text location is only a heuristic.
            "remote_flag_reported": workplace == "remote",
            "company_size": "",
            "crypto": crypto,
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
    match_mode: str = "all_significant",
    include_founding: bool = True,
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
            pool.submit(
                _fetch_company_postings, slug, roles,
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
                logger.warning("Lever/%s failed: %s", slug, e)

    results = rank_by_relevance(results, roles)[:max_results]
    logger.info("Lever: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
