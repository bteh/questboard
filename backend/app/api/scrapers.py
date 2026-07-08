"""Scraper sources endpoint: serves registry metadata to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.scrapers import ScraperSource

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
