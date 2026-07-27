"""Scraper sources endpoints: registry metadata and per-source health.

/sources is app furniture (settings reads it) and stays open; the ops
surfaces (/health, /runs, /schedule) are admin-only in hosted mode via
require_ops_access.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.dependencies import require_ops_access
from app.models.database import get_db
from app.services import application_service

from app.schemas.scrapers import (
    BoardScheduleResponse,
    ScraperSource,
    ScrapeRunEntry,
    ScrapeRunsResponse,
    SourceHealthEntry,
    SourceHealthResponse,
    SourceScheduleEntry,
)

router = APIRouter(prefix="/scrapers", tags=["scrapers"])


@router.get("/sources", response_model=list[ScraperSource])
async def list_sources(
    vertical: str | None = Query(
        None,
        description="Vertical to list ('all' for every source). Defaults to career, "
        "so quest sources never show up in career job-board settings",
    ),
) -> list[ScraperSource]:
    """Return metadata for registered scraper sources (career by default)."""
    from job_finder.tools.scrapers import get_all_metadata

    metas = get_all_metadata()
    if vertical != "all":
        wanted = vertical or "career"
        metas = [m for m in metas if getattr(m, "vertical", "career") == wanted]
    return [
        ScraperSource(
            name=m.name,
            display_name=m.display_name,
            url=m.url,
            description=m.description,
            category=m.category,
            enabled_by_default=m.enabled_by_default,
            vertical=getattr(m, "vertical", "career"),
        )
        for m in metas
    ]


@router.get("/health", response_model=SourceHealthResponse, dependencies=[Depends(require_ops_access)])
async def sources_health(
    days: int = Query(14, ge=1, le=90, description="Run-log window in days"),
    db: Session = Depends(get_db),
) -> SourceHealthResponse:
    """Per-source health from the scrape run log, worst verdicts first.

    Triage is this one call: a source that broke (failing), silently broke
    (zero_rows while history says it finds rows), or halved (dropped) is at
    the top with its last error line. See docs/source-reliability.md.
    """
    from job_finder.source_health import source_health
    from job_finder.tools.scrapers import get_all_metadata

    display = {m.name: m.display_name for m in get_all_metadata()}
    # Health comes from the run log; what a source is worth comes from this
    # person's own board. Joined here so neither side has to know the other.
    kept = application_service.live_rows_by_source(db)
    entries = [
        SourceHealthEntry(
            source=h.source,
            display_name=display.get(h.source, h.source),
            vertical=h.vertical,
            verdict=h.verdict,
            last_run_at=h.last_run_at,
            last_finish_reason=h.last_finish_reason,
            last_rows=h.last_rows,
            median_rows=h.median_rows,
            runs_seen=h.runs_seen,
            error_sample=h.error_sample,
            last_seconds=h.last_seconds,
            kept_rows=kept.get(h.source.strip().lower(), 0),
        )
        for h in source_health(days=days)
    ]
    attention = sum(1 for e in entries if e.verdict in ("failing", "zero_rows", "dropped"))
    return SourceHealthResponse(sources=entries, needs_attention=attention)


@router.get("/runs", response_model=ScrapeRunsResponse, dependencies=[Depends(require_ops_access)])
async def scrape_runs(
    source: str | None = Query(None, max_length=64, description="Limit to one source"),
    days: int = Query(14, ge=1, le=90, description="Run-log window in days"),
    limit: int = Query(200, ge=1, le=500, description="Newest rows to return"),
) -> ScrapeRunsResponse:
    """Raw run-log rows, newest first: the drill-down behind the health verdicts."""
    from job_finder.models.database import get_recent_scrape_runs
    from job_finder.tools.scrapers import get_all_metadata

    display = {m.name: m.display_name for m in get_all_metadata()}
    rows = get_recent_scrape_runs(days=days, source=source, limit=limit)
    return ScrapeRunsResponse(
        runs=[
            ScrapeRunEntry(
                source=r.source,
                display_name=display.get(r.source, r.source),
                vertical=r.vertical or "career",
                started_at=r.started_at,
                duration_s=r.duration_s or 0.0,
                finish_reason=r.finish_reason,
                rows_found=r.rows_found or 0,
                rows_invalid=getattr(r, "rows_invalid", 0) or 0,
                error_sample=r.error_sample or "",
            )
            for r in rows
        ]
    )


@router.get("/schedule", response_model=BoardScheduleResponse, dependencies=[Depends(require_ops_access)])
async def board_schedule(request: Request) -> BoardScheduleResponse:
    """Every schedulable source with its cadence and due state, soonest first.

    scheduler_running says whether this process owns a live sweep loop;
    the per-source rows are true either way (they read the run log).
    """
    from job_finder.schedule import board_schedule as compute_schedule

    entries = compute_schedule()
    scheduler = getattr(request.app.state, "scheduler", None)
    return BoardScheduleResponse(
        scheduler_running=scheduler is not None,
        sources=[
            SourceScheduleEntry(
                source=s.name,
                display_name=s.display_name,
                vertical=s.vertical,
                refresh_hours=s.refresh_hours,
                last_attempt_at=s.last_attempt_at,
                due_at=s.due_at,
                due_now=s.due(),
                failure_streak=s.failure_streak,
                breaker_open=s.breaker_open,
            )
            for s in entries
        ],
    )
