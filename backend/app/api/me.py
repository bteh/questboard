"""Hosted identity bootstrap endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.database import get_db
from app.schemas.workspace import HostedBootstrapResponse, WorkspaceSessionResponse
from app.services import workspace_service

router = APIRouter(tags=["me"])


@router.get("/me", response_model=HostedBootstrapResponse | WorkspaceSessionResponse)
def get_me(
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if settings.hosted_mode:
        return workspace_service.get_hosted_bootstrap(db, request)

    return WorkspaceSessionResponse(
        workspace_id="local",
        expires_at=datetime.now(timezone.utc),
        hosted_mode=False,
        csrf_required=False,
        llm_optional=True,
    )
