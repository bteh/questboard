from __future__ import annotations

from pydantic import BaseModel, Field


class QuestRefreshRequest(BaseModel):
    """POST /quests/refresh body. Verticals are validated in the route
    against job_finder.quests.QUEST_VERTICALS so career can never sneak in."""

    verticals: list[str]
    query: str | None = Field(None, max_length=200)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    radius_miles: int | None = Field(None, ge=1, le=500)


class QuestSourceCounts(BaseModel):
    found: int = 0
    saved: int = 0
    deduped: int = 0
    skipped_stale: int = 0
    expired: int = 0
    # set when the sweep did not run (mass-expiry guard, missing history)
    expiry_skipped: str | None = None


class QuestRefreshSummary(BaseModel):
    verticals: list[str] = []
    found: int = 0
    saved: int = 0
    deduped: int = 0
    skipped_stale: int = 0
    expired: int = 0
    sources: dict[str, QuestSourceCounts] = {}
