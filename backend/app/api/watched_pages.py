"""Places I'd work at: careers pages every quest refresh reads. Local only."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import (
    get_workspace_context,
    get_workspace_context_csrf,
    reject_legacy_route_in_hosted_mode,
)
from app.models.database import get_db
from app.schemas.watched_pages import WatchedPageAddRequest, WatchedPagesResponse
from app.security import enforce_rate_limit, request_identity
from app.services import watched_pages_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watched-pages", tags=["watched-pages"])

_LOCAL_ONLY = "Watched pages live on your own computer"


@router.get("", response_model=WatchedPagesResponse)
def list_pages(
    context = Depends(get_workspace_context),
    db: Session = Depends(get_db),
):
    reject_legacy_route_in_hosted_mode(_LOCAL_ONLY)
    return watched_pages_service.listing(db)


@router.post("", response_model=WatchedPagesResponse)
def add_page(
    req: WatchedPageAddRequest,
    request: Request,
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    """Read the pasted page once, then watch it. A bad link or an unreadable
    page is a 422 with a plain reason."""
    reject_legacy_route_in_hosted_mode(_LOCAL_ONLY)
    enforce_rate_limit(
        "watched-pages",
        request_identity(request, context.workspace.id),
        limit=get_settings().search_rate_limit_per_minute,
        db=db,
    )
    from app.services.local_agent_service import saved_place

    try:
        return watched_pages_service.add_page(
            db, req.url, saved_place(db, context.workspace.id) or None
        )
    except watched_pages_service.WatchedPageError as exc:
        raise HTTPException(422, detail=str(exc))


@router.delete("/{page_id}", response_model=WatchedPagesResponse)
def remove_page(
    page_id: int,
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    reject_legacy_route_in_hosted_mode(_LOCAL_ONLY)
    return watched_pages_service.remove_page(db, page_id)
