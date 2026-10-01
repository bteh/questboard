"""Companies already on the user's board join the every-pull ATS set.

Airbnb rows reached the board through LinkedIn and BuiltIn every week while
its own Greenhouse board sat in the cold catalog rotation, scanned once
every ~21 pulls. A company the board already shows is one the user's search
keeps landing on, so its ATS board belongs in the set scanned on every pull.

The cap is on resolved boards per host, not on names: most of the names
with the most rows come from LinkedIn and Indeed and resolve to no board at
all, so a name cap kept 99 of 368 resolvable boards (Oct 1 2026).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from job_finder.company_taxonomy import normalize_company_key
from job_finder.config.company_catalog import resolve_watchlist

logger = logging.getLogger(__name__)

BOARD_WINDOW_DAYS = 45
BOARD_NAME_FETCH = 1500
BOARD_HOST_CAP = 120


def companies_on_board(
    *,
    days: int = BOARD_WINDOW_DAYS,
    cap: int = BOARD_NAME_FETCH,
    workspace_id: str | None = None,
) -> list[str]:
    """Distinct companies of career rows found in the last ``days`` days.

    Status found only, any source, most rows first so every cap downstream
    keeps the companies the board shows most.
    """
    from sqlalchemy import func

    from job_finder.models.database import (
        ApplicationRecord,
        _close_session,
        get_session,
        scoped_applications,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    row_count = func.count(ApplicationRecord.id)
    session = get_session()
    try:
        query = scoped_applications(session).filter(
            ApplicationRecord.status == "found",
            ApplicationRecord.date_found >= cutoff,
            ApplicationRecord.company != "",
        )
        if workspace_id:
            query = query.filter(ApplicationRecord.workspace_id == workspace_id)
        rows = (
            query.with_entities(ApplicationRecord.company, row_count)
            .group_by(ApplicationRecord.company)
            .order_by(row_count.desc(), ApplicationRecord.company)
            .limit(max(0, int(cap)))
            .all()
        )
    finally:
        _close_session()
    return [str(company) for company, _count in rows if str(company or "").strip()]


def _entry_key(entry: Any) -> str:
    name = entry.get("name", "") if isinstance(entry, dict) else str(entry or "")
    return normalize_company_key(name)


def _entry_board(entry: Any) -> tuple[str, str] | None:
    if not isinstance(entry, dict) or not entry.get("slug"):
        return None
    ats = str(entry.get("ats") or "unknown")
    return None if ats == "unknown" else (ats, str(entry["slug"]).strip().lower())


def _auto_board_entries(
    names: list[str],
    taken_names: set[str],
    taken_boards: set[tuple[str, str]],
    *,
    per_host_cap: int,
    resolve: Callable[[list[str]], list[dict[str, str]]],
) -> list[dict[str, str]]:
    """Resolve ``names`` (row-count order) to boards, at most ``per_host_cap`` per host."""
    fresh = []
    for name in names:
        key = _entry_key(name)
        if key and key not in taken_names:
            taken_names.add(key)
            fresh.append(str(name).strip())
    per_host: dict[str, int] = {}
    chosen: list[dict[str, str]] = []
    for entry in resolve(fresh):
        board = _entry_board(entry)
        if board is None or board in taken_boards:
            continue
        host = board[0]
        if per_host.get(host, 0) >= per_host_cap:
            continue
        per_host[host] = per_host.get(host, 0) + 1
        taken_boards.add(board)
        chosen.append({"name": entry["name"], "ats": host, "slug": board[1]})
    return chosen


def watchlist_with_board_companies(
    raw_watchlist: list,
    *,
    workspace_id: str | None = None,
    per_host_cap: int = BOARD_HOST_CAP,
    fetch: Callable[..., list[str]] = companies_on_board,
    resolve: Callable[[list[str]], list[dict[str, str]]] = resolve_watchlist,
) -> list:
    """Append resolved boards of companies on the board, after the user's own entries.

    The user's watchlist comes first and untouched; auto entries carry their
    ats/slug so the pipeline trusts them verbatim. Never raises: a database
    problem logs and leaves the watchlist as given, because the pull must not
    depend on this lane.
    """
    merged = list(raw_watchlist)
    try:
        names = fetch(workspace_id=workspace_id, cap=BOARD_NAME_FETCH)
    except Exception as exc:
        logger.warning("Board companies unavailable for the ATS watchlist (non-fatal): %s", exc)
        return merged
    taken_names = {_entry_key(entry) for entry in merged}
    taken_boards = {b for b in (_entry_board(entry) for entry in merged) if b}
    added = _auto_board_entries(
        names, taken_names, taken_boards, per_host_cap=per_host_cap, resolve=resolve,
    )
    if added:
        logger.info("ATS watchlist: +%d boards of companies already on the board", len(added))
    return merged + added
