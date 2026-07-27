"""Ashby — Company career page scraper via public job board API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from job_finder.tools.scrapers._ats_discovery import DeadBoards
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    ATS_FETCH_WORKERS,
    _clean_company_name,
    _get_json,
    _load_seed_slugs,
    _match_roles,
    _match_roles_crypto,
    rank_by_relevance,
    date_confidence_for,
    is_crypto_company,
)

logger = logging.getLogger(__name__)

# Seeded from scrapers/data/ashby_seed.txt at import. Ashby is the newer ATS
# preferred by AI-native and modern dev-tool startups — high-signal coverage
# for the Series A–C cohort. Watchlist entries are additive.
_ASHBY_COMPANIES: list[str] = _load_seed_slugs("ashby_seed.txt")

# Ashby comp-component intervals -> the shared salary_period vocabulary
# (PAY_PERIOD_FACTORS keys). The API emits '1 HOUR', '1 YEAR', etc.
_INTERVAL_PERIODS: dict[str, str] = {
    "1 HOUR": "hourly",
    "1 DAY": "daily",
    "1 WEEK": "weekly",
    "1 MONTH": "monthly",
    "1 YEAR": "annual",
}


def _interval_to_period(interval: object) -> str:
    """Map an Ashby compensation interval to a salary_period value ('' unknown)."""
    return _INTERVAL_PERIODS.get(str(interval or "").strip().upper(), "")


def _fetch_company_jobs(
    slug: str,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    on_status=None,
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
        on_status=on_status,
    )
    if not data or "jobs" not in data:
        return []

    # Crypto/web3 companies (e.g. Alchemy, Magic Eden) use crypto-aware role
    # matching so titles like "Smart Contract Engineer" survive even when they
    # don't word-match the user's target roles — otherwise the scraper drops
    # them here, before the pipeline's crypto rescue can ever see them.
    crypto = is_crypto_company(slug)

    jobs: list[dict] = []
    for job in data["jobs"]:
        title = job.get("title", "")
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

        description = (job.get("descriptionPlain", "") or "")[:3000]
        location = job.get("location", "")
        is_remote = job.get("isRemote", False) or job.get("workplaceType", "").lower() == "remote"

        # Parse compensation: raw values + the currency and interval Ashby
        # states alongside them. An hourly component stays a raw hourly rate
        # with salary_period='hourly'; annualization happens downstream in
        # finalize_scraper_jobs via the salary_*_annualized convention.
        salary_min = None
        salary_max = None
        salary_currency = ""
        salary_period = ""
        comp = job.get("compensation")
        if comp and isinstance(comp, dict):
            tiers = comp.get("compensationTiers", [])
            if tiers:
                components = tiers[0].get("components", [])
                for c in components:
                    if c.get("compensationType") == "Salary":
                        salary_min = c.get("minValue")
                        salary_max = c.get("maxValue")
                        salary_currency = c.get("currencyCode") or ""
                        salary_period = _interval_to_period(c.get("interval"))
                        break

        published_at = job.get("publishedAt", "")

        jobs.append({
            "title": title,
            "company": _clean_company_name(slug),
            "location": location,
            "url": job.get("jobUrl", ""),
            "source": "ashby",
            "description": description,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_currency": salary_currency,
            "salary_period": salary_period,
            # Structured ATS pay is employer-stated — provenance 'reported'.
            "salary_source": (
                "reported"
                if salary_min is not None or salary_max is not None
                else None
            ),
            "date_posted": published_at,
            "date_confidence": date_confidence_for(published_at),
            "is_remote": is_remote,
            # Ashby's isRemote/workplaceType is a definitive ATS flag — the
            # work-type classifier trusts it over text heuristics.
            "remote_flag_reported": bool(is_remote),
            "company_size": "",
            "crypto": crypto,
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
    workers = min(len(company_list), ATS_FETCH_WORKERS)
    dead = DeadBoards("ashby")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _fetch_company_jobs, slug, roles,
                match_mode=match_mode, include_founding=include_founding,
                on_status=dead.watch(slug),
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

    dead.prune()
    results = rank_by_relevance(results, roles)[:max_results]
    logger.info("Ashby: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
