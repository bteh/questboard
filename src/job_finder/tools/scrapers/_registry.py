"""Scraper plugin registry — decorator-based auto-discovery.

Zero imports from sibling scraper modules to avoid circular deps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScraperMeta:
    name: str               # "remotive" — matches source field in job dicts
    display_name: str        # "Remotive" — UI label
    url: str                 # "https://remotive.com"
    description: str         # one-liner
    category: str            # "remote" | "ats" | "startup" | "crypto" | "community" | "jobspy"
    enabled_by_default: bool
    search_fn: Callable | None  # None for jobspy metadata-only entries


_REGISTRY: dict[str, ScraperMeta] = {}


def register_scraper(
    name: str,
    display_name: str,
    url: str,
    description: str = "",
    category: str = "general",
    enabled_by_default: bool = True,
) -> Callable:
    """Decorator that registers a scraper function with its metadata."""
    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = ScraperMeta(
            name=name,
            display_name=display_name,
            url=url,
            description=description,
            category=category,
            enabled_by_default=enabled_by_default,
            search_fn=fn,
        )
        return fn
    return decorator


def get_registry() -> dict[str, ScraperMeta]:
    """Return the full registry dict (name -> ScraperMeta)."""
    return _REGISTRY


def get_all_metadata() -> list[ScraperMeta]:
    """Return metadata for all registered scrapers (including jobspy)."""
    return list(_REGISTRY.values())


def run_scrapers(
    names: list[str] | None = None,
    roles: list[str] | None = None,
    max_results: int = 25,
    progress: Callable[[str], None] | None = None,
    locations: list[str] | None = None,
    max_days_old: int = 14,
    watchlist_by_ats: dict[str, list[str]] | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict]:
    """Run selected scrapers **in parallel** and merge results.

    Parameters
    ----------
    names : list of scraper names to run, or None for all with search_fn
    roles : target role keywords for filtering
    max_results : cap per individual source
    progress : optional callback ``fn(msg: str)``
    locations : target locations (used by scrapers that support it)
    max_days_old : max age of listings in days (used by scrapers that support it)
    watchlist_by_ats : mapping of ATS name → list of company slugs from user watchlist
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed

    active = names or [
        name for name, meta in _REGISTRY.items()
        if meta.search_fn is not None
    ]
    if not active:
        return []

    _ats_scrapers = {"greenhouse", "lever", "ashby", "workable"}
    # Defensive copy — we may extend this dict with discovered slugs below.
    ats_watchlist: dict[str, list[str]] = {
        k: list(v) for k, v in (watchlist_by_ats or {}).items()
    }
    # ATS scrapers ship with curated seed lists (data/{ats}_seed.txt) that
    # cover 100+ high-signal companies between them. They used to be skipped
    # entirely when the user had no watchlist, which made all those seed
    # companies dead code. Now they always run; the user's watchlist is
    # additive on top via the watchlist_companies kwarg below.
    runnable: list[str] = list(active)

    # Dynamic ATS slug discovery — expand each ATS scraper's watchlist with
    # company slugs harvested from DuckDuckGo for the user's target roles.
    # Cache-first (7-day TTL) so this only hits the network occasionally.
    # Failures are swallowed — ATS scrapers still run on their seed lists.
    if roles:
        try:
            from job_finder.tools.scrapers._ats_discovery import discover_and_cache
        except ImportError as exc:
            logger.warning("ATS discovery unavailable: %s", exc)
            discover_and_cache = None
        if discover_and_cache is not None:
            for ats_name in _ats_scrapers:
                if ats_name not in active:
                    continue
                try:
                    discovered = discover_and_cache(ats_name, list(roles))
                except Exception as exc:
                    logger.warning(
                        "ATS discovery for %s failed (non-fatal): %s", ats_name, exc,
                    )
                    discovered = set()
                if not discovered:
                    continue
                existing = set(ats_watchlist.get(ats_name, []))
                ats_watchlist[ats_name] = sorted(existing | discovered)
                if progress:
                    new_count = len(discovered - existing)
                    meta = _REGISTRY.get(ats_name)
                    display = meta.display_name if meta else ats_name
                    progress(
                        f"  {display}: discovered {new_count} new companies "
                        f"(watchlist now {len(ats_watchlist[ats_name])})"
                    )

    if progress:
        progress(f"Searching {len(runnable)} additional sources in parallel...")

    if not runnable:
        return []

    # Extract role-match strictness from the resolved filter dict so every
    # scraper applies the same `_match_roles` semantics as the pipeline-level
    # role filter. Without this, individual scrapers fall back to the strict
    # default ("all_significant") and silently drop legitimate matches like
    # "Research Engineer" for the role "ai engineer" — which was the largest
    # single throughput drain inside the ATS scrapers.
    _filters = filters or {}
    role_match_kwargs: dict[str, Any] = {
        "match_mode": _filters.get("role_match_mode", "all_significant"),
        "include_founding": _filters.get("include_founding_titles", True),
    }

    def _run_one(name: str) -> tuple[str, list[dict]]:
        meta = _REGISTRY.get(name)
        if not meta or not meta.search_fn:
            logger.warning("Unknown or metadata-only source: %s", name)
            return name, []
        try:
            kwargs: dict[str, Any] = dict(role_match_kwargs)
            if name in _ats_scrapers:
                extra = ats_watchlist.get(name, [])
                if extra:
                    kwargs["watchlist_companies"] = extra
            return name, meta.search_fn(
                roles=roles,
                max_results=max_results,
                locations=locations,
                max_days_old=max_days_old,
                **kwargs,
            )
        except Exception as e:
            logger.warning("Scraper %s failed (non-fatal): %s", name, e)
            return name, []

    all_jobs: list[dict] = []
    workers = min(len(runnable), 8)
    # Per-scraper timeout prevents a single slow/hung scraper from blocking
    # the entire pipeline.  Scrapers that exceed this are logged and skipped.
    scraper_timeout = 60  # seconds

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, n): n for n in runnable}
        try:
            for future in as_completed(futures, timeout=scraper_timeout * 2):
                try:
                    name, jobs = future.result(timeout=scraper_timeout)
                except FuturesTimeout:
                    name = futures.get(future, "unknown")
                    logger.warning("Scraper %s timed out after %ds", name, scraper_timeout)
                    if progress:
                        meta = _REGISTRY.get(name)
                        display = meta.display_name if meta else name
                        progress(f"  {display}: timed out")
                    continue
                except Exception as e:
                    logger.warning("Scraper result error: %s", e)
                    continue
                meta = _REGISTRY.get(name)
                display = meta.display_name if meta else name
                if jobs:
                    all_jobs.extend(jobs)
                    if progress:
                        progress(f"  Found {len(jobs)} jobs from {display}")
                elif progress:
                    progress(f"  {display}: no results")
        except FuturesTimeout:
            logger.warning("Scraper pool timed out after %ds — using partial results", scraper_timeout * 2)
            if progress:
                progress("Warning: some scrapers timed out, using partial results")

    # Shared post-processing: guarantee the contract fields (date_confidence,
    # salary_source, work_type_confidence) on every job from every plugin.
    # Lazy import keeps this module free of sibling imports at import time.
    from job_finder.tools.scrapers._utils import finalize_scraper_jobs

    return finalize_scraper_jobs(all_jobs)
