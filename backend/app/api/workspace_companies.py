"""Workspace companies — the watched-company store the desktop pull reads.

One source of truth. The Companies tab reads/writes the SAME workspace
``target_companies`` that ``build_pipeline_config_override`` feeds to the pull,
so a company added here always drives the next refresh. ATS discovery /
careers-link paste-through and honest-failure messaging are shared with the
legacy profile watchlist via ``watchlist_service``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import get_workspace_context, get_workspace_context_csrf
from app.models.database import get_db
from app.schemas.watchlist import WatchlistAddRequest, WatchlistResponse
from app.security import enforce_rate_limit, request_identity
from app.services import watchlist_service, workspace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace-companies"])


@router.get("/companies", response_model=WatchlistResponse)
def get_companies(
    context = Depends(get_workspace_context),
    db: Session = Depends(get_db),
):
    """List the workspace's watched companies with their resolved ATS boards."""
    result = workspace_service.get_workspace_companies(db, context.workspace.id)
    return WatchlistResponse(profile="workspace", **result)


@router.post("/companies", response_model=WatchlistResponse)
def add_company(
    req: WatchlistAddRequest,
    request: Request,
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    """Add a company by name or careers link to the workspace store.

    A careers link (Greenhouse, Lever, Ashby, Workday) stores its exact board
    token after one verification probe; an unsupported/unconfirmable link is a
    422. A bare name runs auto-discovery; a failed discovery reports so in
    ``message`` and stores an unfinished row the user can complete with a link.
    """
    settings = get_settings()
    enforce_rate_limit(
        "workspace-companies",
        request_identity(request, context.workspace.id),
        limit=settings.search_rate_limit_per_minute,
        db=db,
    )
    name = req.name.strip()
    url = req.url.strip()
    if not name and not url:
        raise HTTPException(400, "Company name or careers link is required")
    try:
        result = workspace_service.add_workspace_company(db, context.workspace.id, name=name, url=url)
    except watchlist_service.BoardUrlError as exc:
        raise HTTPException(422, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to add company to workspace store")
        raise HTTPException(500, detail=str(exc))
    return WatchlistResponse(profile="workspace", **result)


@router.delete("/companies/{name}", response_model=WatchlistResponse)
def remove_company(
    name: str,
    request: Request,
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    """Remove a company (and its cached board) from the workspace store."""
    try:
        result = workspace_service.remove_workspace_company(db, context.workspace.id, name)
    except Exception as exc:
        logger.exception("Failed to remove company from workspace store")
        raise HTTPException(500, detail=str(exc))
    return WatchlistResponse(profile="workspace", **result)
