"""Scraper sources endpoint — serves registry metadata to the frontend."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.scrapers import ScraperSource

router = APIRouter(prefix="/scrapers", tags=["scrapers"])


@router.get("/sources", response_model=list[ScraperSource])
async def list_sources() -> list[ScraperSource]:
    """Return metadata for all registered scraper sources."""
    from job_finder.tools.scrapers import get_all_metadata

    return [
        ScraperSource(
            name=m.name,
            display_name=m.display_name,
            url=m.url,
            description=m.description,
            category=m.category,
            enabled_by_default=m.enabled_by_default,
        )
        for m in get_all_metadata()
    ]
