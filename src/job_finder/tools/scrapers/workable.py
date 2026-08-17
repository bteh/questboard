"""Workable — Bulk company board scraper via the public widget JSON API.

Workable hosts thousands of startup and mid-market boards at
``apply.workable.com/<slug>``. The widget endpoint

    https://apply.workable.com/api/v1/widget/accounts/<slug>?details=true

is public (no auth) and returns every open posting for the account *with the
full HTML description in a single call* — unlike the ``/jobs.md`` feed, which
is title-only. Fetching descriptions inline keeps our scoring quality high
without an N+1 fetch per job.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from job_finder.tools.scrapers._ats_discovery import DeadBoards
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    ATS_FETCH_WORKERS,
    PROTECTED_ROW_KEY,
    WATCHLIST_TIMEOUT,
    _clean_company_name,
    _get_json,
    _load_seed_slugs,
    _match_roles,
    _match_roles_crypto,
    cap_with_protected,
    _strip_html,
    date_confidence_for,
    is_crypto_company,
)

logger = logging.getLogger(__name__)

# Seeded from scrapers/data/workable_seed.txt at import. Watchlist entries
# from the user's config are additive on top of this list.
_WORKABLE_COMPANIES: list[str] = _load_seed_slugs("workable_seed.txt")


def _build_location(job: dict) -> str:
    """Assemble a human location from Workable's split city/country/remote fields.

    The widget payload leaves ``location`` null and splits the pieces across
    ``city``/``country``/``telecommuting``. Prefer "City, Country"; append/emit
    "Remote" when the posting is telecommuting.
    """
    city = (job.get("city") or "").strip()
    country = (job.get("country") or "").strip()
    remote = bool(job.get("telecommuting"))
    parts = [p for p in (city, country) if p]
    base = ", ".join(parts)
    if remote:
        return f"{base} (Remote)" if base else "Remote"
    return base


def _fetch_company_jobs(
    slug: str,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    on_status=None,
    watchlist: bool = False,
) -> list[dict]:
    """Fetch matching jobs for a single Workable account board."""
    # Tight per-board timeout — see ashby.py for rationale. A single slow
    # board must not block the whole search. Watchlist boards get longer:
    # a user-named company must not vanish on a slow or large payload.
    data = _get_json(
        f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
        params={"details": "true"},
        quiet_statuses={404},
        timeout=WATCHLIST_TIMEOUT if watchlist else 6,
        on_status=on_status,
    )
    if not isinstance(data, dict) or "jobs" not in data:
        if watchlist:
            logger.warning("Workable/%s: watchlist board fetch failed", slug)
        return []

    company = data.get("name") or _clean_company_name(slug)
    # Crypto/web3 companies use crypto-aware role matching (see ashby.py).
    crypto = is_crypto_company(slug) or is_crypto_company(company)

    jobs: list[dict] = []
    for job in data.get("jobs") or []:
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

        location = _build_location(job)
        content = job.get("description", "")
        description = _strip_html(content) if content else ""

        # published_on is the real posting date; created_at is the fallback.
        date_posted = job.get("published_on") or job.get("created_at") or ""

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "url": job.get("url") or job.get("shortlink") or "",
            "source": "workable",
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "date_posted": date_posted,
            "date_confidence": date_confidence_for(date_posted),
            "is_remote": bool(job.get("telecommuting")) or "remote" in location.lower(),
            "company_size": "",
            "crypto": crypto,
        })

    if watchlist:
        for job in jobs:
            job[PROTECTED_ROW_KEY] = True
    return jobs


@register_scraper(
    name="workable",
    display_name="Workable",
    url="https://www.workable.com",
    description="Direct job listings from company boards on Workable",
    category="ats",
)
def search_workable(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
    watchlist_companies: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch jobs directly from Workable widget API for known companies."""
    company_list = list(companies or _WORKABLE_COMPANIES)
    watchlist = set(watchlist_companies or [])
    if watchlist_companies:
        company_list.extend(s for s in watchlist_companies if s not in company_list)
    if not company_list:
        logger.info("Workable: no companies configured — add companies to your watchlist")
        return []
    logger.info("Fetching from Workable API for %d companies...", len(company_list))

    results: list[dict] = []
    workers = min(len(company_list), ATS_FETCH_WORKERS)
    dead = DeadBoards("workable")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _fetch_company_jobs, slug, roles,
                match_mode=match_mode, include_founding=include_founding,
                on_status=dead.watch(slug),
                watchlist=slug in watchlist,
            ): slug
            for slug in company_list
        }
        for future in as_completed(futures):
            try:
                jobs = future.result()
                results.extend(jobs)
            except Exception as e:
                slug = futures[future]
                logger.warning("Workable/%s failed: %s", slug, e)

    dead.prune()
    results = cap_with_protected(results, roles, max_results)
    logger.info("Workable: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
