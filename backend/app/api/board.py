"""Board summary: live supply per quest kind, for the board rail.

The kinds come from packages/kinds/kinds.json via job_finder.kinds; stored
rows keep their historical vertical values and are mapped at read time, so
no migration and no scraper edits. Kinds with zero supply are still
returned: supply honesty (a thin kind says so) is the client's call to make.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.dependencies import get_active_workspace_context, workspace_scope_id
from app.models.database import get_db
from app.schemas.board import BoardSummaryResponse, KindSummary

from job_finder.kinds import get_kinds, kind_for_vertical
from job_finder.models.database import ApplicationRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/board", tags=["board"])


@router.get("/summary", response_model=BoardSummaryResponse)
def board_summary(
    profile: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    """Counts per kind plus how many arrived in the last 24 hours."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    day_ago = now - timedelta(hours=24)

    query = (
        db.query(
            ApplicationRecord.vertical,
            func.count(ApplicationRecord.id),
            func.sum(
                case((ApplicationRecord.date_found >= day_ago, 1), else_=0)
            ),
        )
        .filter(ApplicationRecord.vertical != "personal")
        .filter(ApplicationRecord.url_status != "dead")
        # same upcoming semantics as the board list: a taping that already
        # happened is off the board, rows with no event date pass
        .filter(
            or_(
                ApplicationRecord.event_start.is_(None),
                ApplicationRecord.event_start >= now,
            )
        )
    )
    scope = workspace_scope_id(workspace)
    if scope:
        query = query.filter(ApplicationRecord.workspace_id == scope)
    elif profile:
        query = query.filter(ApplicationRecord.profile == profile)
    rows = query.group_by(ApplicationRecord.vertical).all()

    counts: dict[str, int] = {}
    fresh: dict[str, int] = {}
    for vertical, count, new_today in rows:
        kind = kind_for_vertical(vertical or "career")
        if kind is None:
            logger.warning("board summary: row with unknown vertical %r skipped", vertical)
            continue
        counts[kind.id] = counts.get(kind.id, 0) + int(count or 0)
        fresh[kind.id] = fresh.get(kind.id, 0) + int(new_today or 0)

    kinds = [
        KindSummary(
            id=kind.id,
            label=kind.label,
            sub=kind.sub,
            hue=kind.hue,
            order=kind.order,
            count=counts.get(kind.id, 0),
            new_today=fresh.get(kind.id, 0),
        )
        for kind in get_kinds()
    ]
    return BoardSummaryResponse(
        total=sum(counts.values()),
        new_today=sum(fresh.values()),
        kinds=kinds,
    )
