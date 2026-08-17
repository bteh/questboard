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
    category: str            # "remote" | "ats" | "startup" | "vc" | "crypto" | "community" | "jobspy"
    enabled_by_default: bool
    search_fn: Callable | None  # None for jobspy metadata-only entries
    # Board lane this source feeds. Validated against packages/kinds/kinds.json
    # (kind ids or their legacy vertical spellings). The career pipeline only
    # ever runs sources registered with the literal "career" lane.
    vertical: str = "career"
    # Expiry contract, declared by each source about ITSELF (see
    # job_finder.expiry). full_snapshot means one fetch IS the source's
    # entire current set, so absence from two consecutive healthy runs
    # proves an offer is gone. Windowed fetches (newest-N) must never use
    # absence; they declare stale_after_days instead: how long an
    # unconfirmed row may honestly stay on the board.
    full_snapshot: bool = False
    stale_after_days: int | None = None
    # Research tooling, never board content. A research_only source is
    # visible in the registry (so /scrapers/sources and internal tools can
    # use it) but no selection path may run it in a sweep or refresh:
    # reddit tells us WHERE to crawl, it is never itself the content
    # (curation verdict, docs/source-coverage.md).
    research_only: bool = False
    # Refresh cadence, declared by each source about ITSELF (like the
    # expiry contract): how many hours between automatic sweeps. The
    # board scheduler (job_finder.schedule) only ever runs quest sources
    # that declare this; None means manual-only. Pick the source's real
    # publishing rhythm, not "as fast as possible": politeness is part
    # of the trust posture.
    refresh_hours: int | None = None
    # Row contract (job_finder.row_contract): where this source's rows
    # may point. Hosts are registered domains (subdomains pass); paths
    # are required prefixes. None means no gate: bankrewards points at
    # each bank's own offer page by design. Shared structural rules
    # (real title, parseable URL, no future dates) apply regardless.
    allowed_url_hosts: tuple[str, ...] | None = None
    allowed_url_paths: tuple[str, ...] | None = None


_REGISTRY: dict[str, ScraperMeta] = {}
_SCRAPER_POOL_TIMEOUT_SECONDS = 60.0


def register_scraper(
    name: str,
    display_name: str,
    url: str,
    description: str = "",
    category: str = "general",
    enabled_by_default: bool = True,
    vertical: str = "career",
    kind: str | None = None,
    full_snapshot: bool = False,
    stale_after_days: int | None = None,
    research_only: bool = False,
    refresh_hours: int | None = None,
    allowed_url_hosts: tuple[str, ...] | None = None,
    allowed_url_paths: tuple[str, ...] | None = None,
) -> Callable:
    """Decorator that registers a scraper function with its metadata.

    `kind` is the canonical quest-kind id from packages/kinds/kinds.json and is
    what new sources should pass. `vertical` remains as the legacy spelling for
    existing sources; both are validated against the kinds registry so a typo
    fails at import time instead of silently miscategorizing a source.
    """
    from job_finder.kinds import known_vertical_values

    lane = kind or vertical
    if lane not in known_vertical_values():
        raise ValueError(
            f"scraper {name!r} declares unknown kind/vertical {lane!r}; "
            "add it to packages/kinds/kinds.json first"
        )

    def decorator(fn: Callable) -> Callable:
        _REGISTRY[name] = ScraperMeta(
            name=name,
            display_name=display_name,
            url=url,
            description=description,
            category=category,
            enabled_by_default=enabled_by_default,
            search_fn=fn,
            vertical=lane,
            full_snapshot=full_snapshot,
            stale_after_days=stale_after_days,
            research_only=research_only,
            refresh_hours=refresh_hours,
            allowed_url_hosts=allowed_url_hosts,
            allowed_url_paths=allowed_url_paths,
        )
        return fn
    return decorator


def get_registry() -> dict[str, ScraperMeta]:
    """Return the full registry dict (name -> ScraperMeta)."""
    return _REGISTRY


def default_scraper_names() -> list[str]:
    """Scrapers that run when no explicit names are given: career sources only.

    Quest scrapers (vertical != career) run only when a caller names them, so
    no default sweep can route quest listings into the career pipeline.
    """
    return [
        name for name, meta in _REGISTRY.items()
        if meta.search_fn is not None
        and meta.vertical == "career"
        and not meta.research_only
    ]


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
    scraper_kwargs: dict[str, dict[str, Any]] | None = None,
    max_results_by_source: dict[str, int] | None = None,
    outcome_sink: list[dict[str, Any]] | None = None,
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
    scraper_kwargs : optional per-scraper extra kwargs (name -> kwargs), used by
        quest ingestion to hand query/geo hints only to scrapers that take them
    max_results_by_source : optional per-source result ceilings. Quest ingestion
        uses this to let declared full snapshots fetch their complete roster
        without inflating every windowed source.
    outcome_sink : optional caller-owned list populated with one structured
        outcome per attempted source. This lets a whole refresh publish an
        exact coverage receipt without re-reading the run log by timestamp.
    """
    import queue
    import threading
    import time

    active = names or default_scraper_names()
    if not active:
        return []

    # Workday has no seed .txt or DDG discovery (its universe is the employer
    # YAML); _ats_discovery guards unknown hosts, so it only receives the
    # watchlist_companies kwarg here.
    _ats_scrapers = {"greenhouse", "lever", "ashby", "workable", "workday"}
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
            from job_finder.tools.scrapers._ats_discovery import (
                discover_and_cache,
                verified_rotation_slugs,
            )
        except ImportError as exc:
            logger.warning("ATS discovery unavailable: %s", exc)
            discover_and_cache = None
            verified_rotation_slugs = None
        if discover_and_cache is not None:
            # Each host's discovery is independent.  A cold first run used to
            # wait for four 15-20s DDG sweeps serially before *any* source could
            # start (74s in the packaged runtime). Run the same four sweeps in
            # parallel; the result sets and cache semantics are unchanged.
            from concurrent.futures import ThreadPoolExecutor

            active_ats = sorted(_ats_scrapers.intersection(active))

            def _discover_ats(ats_name: str) -> tuple[str, set[str], set[str]]:
                try:
                    discovered = discover_and_cache(ats_name, list(roles))
                except Exception as exc:
                    logger.warning(
                        "ATS discovery for %s failed (non-fatal): %s", ats_name, exc,
                    )
                    discovered = set()
                try:
                    rotated = (
                        verified_rotation_slugs(ats_name)
                        if verified_rotation_slugs is not None
                        else set()
                    )
                except Exception as exc:
                    logger.warning(
                        "Verified ATS rotation for %s failed (non-fatal): %s",
                        ats_name,
                        exc,
                    )
                    rotated = set()
                return ats_name, discovered, rotated

            with ThreadPoolExecutor(max_workers=max(1, len(active_ats))) as discovery_pool:
                coverage_results = list(discovery_pool.map(_discover_ats, active_ats))

            for ats_name, discovered, rotated in coverage_results:
                coverage = discovered | rotated
                if not coverage:
                    continue
                existing = set(ats_watchlist.get(ats_name, []))
                ats_watchlist[ats_name] = sorted(existing | coverage)
                if progress:
                    new_count = len(discovered - existing)
                    rotation_count = len(rotated - existing - discovered)
                    meta = _REGISTRY.get(ats_name)
                    display = meta.display_name if meta else ats_name
                    progress(
                        f"  {display}: {new_count} discovered + "
                        f"{rotation_count} catalog rotation companies "
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

    def _run_one(name: str) -> tuple[str, list[dict], dict]:
        import time as _time
        from datetime import datetime as _dt, timezone as _tz

        meta = _REGISTRY.get(name)
        outcome: dict[str, Any] = {
            "source": name,
            "vertical": meta.vertical if meta else "career",
            "started_at": _dt.now(_tz.utc).replace(tzinfo=None),
            "duration_s": 0.0,
            "finish_reason": "ok",
            "rows_found": 0,
            "error_sample": "",
        }
        if not meta or not meta.search_fn:
            logger.warning("Unknown or metadata-only source: %s", name)
            outcome["finish_reason"] = "exception"
            outcome["error_sample"] = "unknown or metadata-only source"
            return name, [], outcome
        t0 = _time.monotonic()
        try:
            source_max_results = max(
                1,
                int((max_results_by_source or {}).get(name, max_results)),
            )
            kwargs: dict[str, Any] = dict(role_match_kwargs)
            if name in _ats_scrapers:
                extra = ats_watchlist.get(name, [])
                if extra:
                    kwargs["watchlist_companies"] = extra
            if scraper_kwargs and name in scraper_kwargs:
                kwargs.update(scraper_kwargs[name])
            jobs = meta.search_fn(
                roles=roles,
                max_results=source_max_results,
                locations=locations,
                max_days_old=max_days_old,
                **kwargs,
            )
            raw_count = len(jobs or [])
            outcome["duration_s"] = round(_time.monotonic() - t0, 2)
            # The row contract: a row publishes only when it is actionable
            # (job_finder.row_contract). Rejects are counted, never silent,
            # so a validator that suddenly rejects everything is as visible
            # in the run log as a source that broke.
            from job_finder.row_contract import validate_rows

            jobs, rejected = validate_rows(jobs or [], meta)
            if rejected:
                outcome["rows_invalid"] = len(rejected)
                sample_row, sample_reason = rejected[0]
                logger.warning(
                    "%s: %d row(s) failed the row contract (first: %s %r)",
                    name, len(rejected), sample_reason,
                    str(sample_row.get("title", ""))[:80],
                )
            # One common discovery boundary for every source. Portfolio boards
            # and aggregators can now teach Questboard a company's industry,
            # ecosystem, and official ATS URL without source-specific glue.
            if jobs and meta.vertical == "career":
                try:
                    from job_finder.company_taxonomy import observe_jobs

                    observe_jobs(jobs, source_category=meta.category)
                except Exception as exc:
                    logger.warning(
                        "Company discovery observation for %s failed (non-fatal): %s",
                        name,
                        exc,
                    )
            outcome["rows_found"] = len(jobs)
            if not jobs:
                outcome["finish_reason"] = "zero_rows"
            elif (
                meta.vertical != "career"
                and raw_count >= max(1, int(source_max_results * 0.95))
            ):
                # A quest source at (or very near) its caller-imposed cap has
                # not proved that it returned the complete live set. Calling
                # that run healthy is especially dangerous for full-snapshot
                # expiry: rows just beyond the cap could be tombstoned as
                # absent. Keep the useful rows, but record honest coverage.
                outcome["finish_reason"] = "partial"
                outcome["error_sample"] = (
                    f"result cap reached ({raw_count}/{source_max_results}); "
                    "coverage may be truncated"
                )
            return name, jobs, outcome
        except Exception as e:
            logger.warning("Scraper %s failed (non-fatal): %s", name, e)
            outcome["duration_s"] = round(_time.monotonic() - t0, 2)
            outcome["finish_reason"] = "exception"
            outcome["error_sample"] = str(e)[:500]
            return name, [], outcome

    all_jobs: list[dict] = []
    outcomes: list[dict] = []
    seen_sources: set[str] = set()
    # Every source gets its own DAEMON thread. ThreadPoolExecutor's context
    # manager always calls shutdown(wait=True), so its apparent timeout still
    # blocked forever on a hung source. A daemon fan-out plus one shared result
    # queue enforces a real wall-clock ceiling and lets healthy source rows save.
    scraper_timeout = max(0.01, float(_SCRAPER_POOL_TIMEOUT_SECONDS))
    result_queue: queue.Queue[tuple[str, list[dict], dict]] = queue.Queue()

    def _run_and_publish(name: str) -> None:
        result_queue.put(_run_one(name))

    for name in runnable:
        threading.Thread(
            target=_run_and_publish,
            args=(name,),
            name=f"questboard-scraper-{name}",
            daemon=True,
        ).start()

    deadline = time.monotonic() + scraper_timeout
    while len(seen_sources) < len(runnable):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            name, jobs, outcome = result_queue.get(timeout=remaining)
        except queue.Empty:
            break
        seen_sources.add(name)
        outcomes.append(outcome)
        meta = _REGISTRY.get(name)
        display = meta.display_name if meta else name
        if jobs:
            all_jobs.extend(jobs)
            if progress:
                progress(f"  Found {len(jobs)} jobs from {display}")
        elif progress:
            progress(f"  {display}: no results")

    if len(seen_sources) < len(runnable):
        logger.warning("Scraper pool timed out after %.1fs — using partial results", scraper_timeout)
        if progress:
            progress("Warning: some scrapers timed out, using partial results")

    # A hung source must not vanish from the record: it looks exactly like a
    # healthy quiet day otherwise. Every runnable source gets a run-log row.
    for name in runnable:
        if name in seen_sources:
            continue
        meta = _REGISTRY.get(name)
        outcomes.append({
            "source": name,
            "vertical": meta.vertical if meta else "career",
            "duration_s": scraper_timeout,
            "finish_reason": "timeout",
            "rows_found": 0,
            "error_sample": f"no result within {scraper_timeout:g}s",
        })
        if progress:
            display = meta.display_name if meta else name
            progress(f"  {display}: timed out")
    try:
        from job_finder.models.database import record_scrape_runs
        record_scrape_runs(outcomes)
    except Exception as exc:
        logger.warning("scrape run log unavailable (non-fatal): %s", exc)

    if outcome_sink is not None:
        # Copy each row so the caller cannot mutate the same dictionaries the
        # run log just received.
        outcome_sink.extend(dict(outcome) for outcome in outcomes)

    # Shared post-processing: guarantee the contract fields (date_confidence,
    # salary_source, work_type_confidence) on every job from every plugin.
    # Lazy import keeps this module free of sibling imports at import time.
    from job_finder.tools.scrapers._utils import finalize_scraper_jobs

    return finalize_scraper_jobs(all_jobs)
