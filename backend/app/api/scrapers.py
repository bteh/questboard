"""Scraper sources endpoints: registry metadata and per-source health."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.scrapers import ScraperSource, SourceHealthEntry, SourceHealthResponse

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


@router.get("/health", response_model=SourceHealthResponse)
async def sources_health(
    days: int = Query(14, ge=1, le=90, description="Run-log window in days"),
) -> SourceHealthResponse:
    """Per-source health from the scrape run log, worst verdicts first.

    Triage is this one call: a source that broke (failing), silently broke
    (zero_rows while history says it finds rows), or halved (dropped) is at
    the top with its last error line. See docs/source-reliability.md.
    """
    from job_finder.source_health import source_health
    from job_finder.tools.scrapers import get_all_metadata

    display = {m.name: m.display_name for m in get_all_metadata()}
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
        )
        for h in source_health(days=days)
    ]
    attention = sum(1 for e in entries if e.verdict in ("failing", "zero_rows", "dropped"))
    return SourceHealthResponse(sources=entries, needs_attention=attention)
