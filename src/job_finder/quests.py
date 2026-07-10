"""Quest ingestion: run quest-vertical scrapers and persist quest rows.

Standalone by design. This path never invokes the career pipeline, role
filters, resume scoring, or any row-deletion sweep. Dedup rides the existing
job_url upsert in save_application.
"""

from __future__ import annotations

import inspect
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from job_finder.kinds import known_vertical_values
from job_finder.tools.scrapers._registry import get_registry, run_scrapers

logger = logging.getLogger(__name__)


def quest_verticals() -> tuple[str, ...]:
    """Every vertical a quest refresh may target: the registry's vocabulary
    minus 'career' (the pipeline path). Derived, never listed by hand, so a
    new kind in kinds.json is refreshable the moment its first scraper ships.
    """
    return tuple(sorted(known_vertical_values() - {"career"}))


# Kept as a module attribute for existing callers; same derived value.
QUEST_VERTICALS = quest_verticals()


def _accepted_geo_kwargs(fn: Callable, candidates: dict[str, Any]) -> dict[str, Any]:
    """Subset of candidates the scraper declares as named parameters.

    Every scraper tolerates **kwargs, but query/geo hints only mean something
    to scrapers that declare them (e.g. clinicaltrials), so the rest never
    receive silent no-op kwargs.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    return {
        key: value
        for key, value in candidates.items()
        if value is not None
        and key in params
        and params[key].kind is not inspect.Parameter.VAR_KEYWORD
    }


def _to_naive_utc(value: object) -> datetime | None:
    """ISO string or datetime to naive UTC datetime (how SQLite stores it)."""
    if isinstance(value, datetime):
        dt = value
    else:
        from job_finder.tools.scrapers._utils import _parse_posted_date

        dt = _parse_posted_date(value)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _new_counts() -> dict[str, int]:
    return {"found": 0, "saved": 0, "deduped": 0, "skipped_stale": 0}


def run_quest_search(
    verticals: list[str],
    *,
    query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_miles: int | None = None,
    workspace_id: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Run the quest scrapers for the requested verticals and persist rows.

    Selects registry scrapers whose vertical is in ``verticals`` (career is
    never selected, whatever the caller asks for), runs them via
    run_scrapers, then saves each emitted row with the quest kwargs. Rows
    whose event_start is already in the past are skipped as stale. Returns a
    summary with totals and per-source counts.
    """
    requested = {v for v in verticals if v != "career"}
    registry = get_registry()
    names = [
        name
        for name, meta in registry.items()
        if meta.search_fn is not None and meta.vertical in requested
    ]

    summary: dict[str, Any] = {
        "verticals": sorted(requested),
        "found": 0,
        "saved": 0,
        "deduped": 0,
        "skipped_stale": 0,
        "sources": {name: _new_counts() for name in names},
    }
    if not names:
        return summary

    geo = {"query": query, "lat": lat, "lon": lon, "radius_miles": radius_miles}
    scraper_kwargs: dict[str, dict[str, Any]] = {}
    for name in names:
        extra = _accepted_geo_kwargs(registry[name].search_fn, geo)
        if extra:
            scraper_kwargs[name] = extra

    rows = run_scrapers(
        names=names,
        max_results=50,
        progress=progress,
        scraper_kwargs=scraper_kwargs or None,
    )

    # Lazy import so this module always talks to the live database module
    # (tests re-import it against a fresh SQLite file).
    from job_finder.models import database

    # New rows get ids above this watermark; anything at or below it that
    # save_application hands back was already known (URL upsert).
    from sqlalchemy import func

    session = database.get_session()
    try:
        start_max_id = (
            session.query(func.max(database.ApplicationRecord.id)).scalar() or 0
        )
    finally:
        database._close_session()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sources: dict[str, dict[str, int]] = summary["sources"]
    seen_ids: set[int] = set()

    for row in rows:
        source = str(row.get("source") or "")
        counts = sources.setdefault(source, _new_counts())
        counts["found"] += 1
        summary["found"] += 1

        meta = registry.get(source)
        vertical = str(row.get("vertical") or (meta.vertical if meta else ""))
        title = str(row.get("title") or "")
        if (
            vertical == "career"
            or vertical not in database.APPLICATION_VERTICALS
            or not title
        ):
            logger.warning("Skipping malformed quest row from %s: %r", source, title[:80])
            continue

        event_start = _to_naive_utc(row.get("event_start"))
        if event_start is not None and event_start < now:
            counts["skipped_stale"] += 1
            summary["skipped_stale"] += 1
            continue

        quest = row.get("quest")
        record = database.save_application(
            job_title=title,
            company=str(row.get("company") or ""),
            location=str(row.get("location") or ""),
            job_url=str(row.get("url") or ""),
            source=source,
            description=str(row.get("description") or ""),
            is_remote=bool(row.get("is_remote", False)),
            salary_min=row.get("salary_min"),
            salary_max=row.get("salary_max"),
            salary_currency=str(row.get("salary_currency") or ""),
            salary_period=str(row.get("salary_period") or ""),
            salary_source=row.get("salary_source"),
            date_posted=row.get("date_posted"),
            date_confidence=row.get("date_confidence"),
            vertical=vertical,
            event_start=event_start,
            event_end=_to_naive_utc(row.get("event_end")),
            is_rolling=bool(row.get("is_rolling", False)),
            first_quest_ok=bool(row.get("first_quest_ok", False)),
            quest_json=json.dumps(quest) if isinstance(quest, dict) and quest else "",
            workspace_id=workspace_id,
        )
        if record is None or record.id in seen_ids or record.id <= start_max_id:
            counts["deduped"] += 1
            summary["deduped"] += 1
            continue
        seen_ids.add(record.id)
        counts["saved"] += 1
        summary["saved"] += 1

    for name, counts in sources.items():
        if counts["found"] == 0:
            logger.warning("Quest source %s returned no rows; dead or empty?", name)

    if progress:
        progress(
            f"Quest refresh: {summary['saved']} saved, {summary['deduped']} already known, "
            f"{summary['skipped_stale']} past events skipped"
        )
    return summary
