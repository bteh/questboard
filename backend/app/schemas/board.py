"""Board summary shapes: per-kind supply counts the board rail renders."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class KindSummary(BaseModel):
    id: str
    label: str
    sub: str
    hue: str
    order: int
    count: int
    new_today: int


class BoardSummaryResponse(BaseModel):
    total: int
    new_today: int
    # last time a quest source ran healthy, from the scrape run log; None
    # until the first refresh
    checked_at: datetime | None = None
    kinds: list[KindSummary]
