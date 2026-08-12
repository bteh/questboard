"""Board summary shapes: per-kind supply counts the board rail renders."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.search import SourceCoverage


class KindSummary(BaseModel):
    id: str
    label: str
    sub: str
    hue: str
    order: int
    count: int
    new_today: int


class CareerRefreshReceipt(BaseModel):
    run_id: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    jobs_found: int = 0
    new_jobs: int = 0
    error: str | None = None
    source_coverage: SourceCoverage | None = None


class BoardSummaryResponse(BaseModel):
    total: int
    new_today: int
    # last time a quest source ran healthy, from the scrape run log; None
    # until the first refresh
    checked_at: datetime | None = None
    # Career freshness is a COMPLETED whole pull, not the newest individual
    # source response. Side quests retain their independent source cadence.
    career_checked_at: datetime | None = None
    side_quest_checked_at: datetime | None = None
    # Newest Find Work attempt, including the exact per-source completion
    # receipt when available. This survives page reloads and app restarts.
    career_refresh: CareerRefreshReceipt | None = None
    kinds: list[KindSummary]
