"""Board summary shapes: per-kind supply counts the board rail renders."""

from __future__ import annotations

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
    kinds: list[KindSummary]
