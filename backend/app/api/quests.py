"""Quest refresh endpoint: explicitly runs quest-vertical scrapers.

Deliberately separate from /search: career refresh keeps its pipeline run
machinery, quest ingestion is a small synchronous sweep (a handful of fast
fetches) that returns its summary on the same request instead of a run id.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import get_active_workspace_context_csrf, workspace_scope_id
from app.models.database import get_db
from app.schemas.quests import QuestRefreshRequest, QuestRefreshSummary
from app.security import enforce_rate_limit, request_identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quests", tags=["quests"])


@router.post("/refresh", response_model=QuestRefreshSummary)
def refresh_quests(
    req: QuestRefreshRequest,
    request: Request,
    workspace = Depends(get_active_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    """Run the quest scrapers for the requested verticals and save the rows."""
    from job_finder.quests import QUEST_VERTICALS, run_quest_search

    invalid = [v for v in req.verticals if v not in QUEST_VERTICALS]
    if not req.verticals or invalid:
        allowed = ", ".join(QUEST_VERTICALS)
        raise HTTPException(
            400,
            f"verticals must be a non-empty subset of {{{allowed}}}; "
            "career refresh stays on /search/run",
        )

    if get_settings().hosted_mode:
        # The hosted board is one shared pool the scheduler sweeps on each
        # source's declared cadence; per-visitor sweeps would duplicate it.
        raise HTTPException(
            403,
            "The board restocks itself here; fresh quests land on their own.",
        )

    enforce_rate_limit(
        "quests-refresh",
        request_identity(request, workspace.workspace.id if workspace else None),
        limit=get_settings().search_rate_limit_per_minute,
        db=db if workspace else None,
    )

    logger.info("Quest refresh: verticals=%s query=%r", req.verticals, req.query)
    summary = run_quest_search(
        req.verticals,
        query=req.query,
        lat=req.lat,
        lon=req.lon,
        radius_miles=req.radius_miles,
        # local rows join the one pool
        workspace_id=workspace_scope_id(workspace),
    )
    return QuestRefreshSummary(**summary)
