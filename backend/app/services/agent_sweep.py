"""Fill the connected agent's compact search_work page from the whole lane.

The agent sees the same eligible lane as the board, so the page decides what
the agent judges next. Rows whose verdict is missing or stale lead; current
verdicts follow as global rank anchors. Nov 3 2026: a newest-first page left
343 of 599 lane rows unranked forever (tests/test_ranking_coverage_nov3.py).
"""
from __future__ import annotations

from typing import Callable, TypeVar

Row = TypeVar("Row")

_ANCHOR_CAP = 10


def sweep_page(
    needs_review: list[Row],
    current: list[Row],
    *,
    page_size: int,
    select: Callable[[list[Row], int], list[Row]],
) -> list[Row]:
    """Return at most page_size rows: needs_review first, then anchors.

    select(rows, limit) must return rows in its own priority order. Up to
    min(10, page_size // 5) anchor slots stay reserved while a backlog
    exists, because the agent needs current ranks to place new judgments
    globally (tests/test_mcp_result_size.py pins the count).
    """
    if not needs_review:
        return select(current, page_size) if current else []
    reserve = min(len(current), _ANCHOR_CAP, page_size // 5)
    unseen = select(needs_review, page_size - reserve)
    anchors = select(current, reserve) if reserve else []
    return unseen + anchors
