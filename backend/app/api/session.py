"""Hosted anonymous session bootstrap endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.workspace import WorkspaceSessionResponse
from app.services import workspace_service

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/bootstrap", response_model=WorkspaceSessionResponse)
def bootstrap_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    return workspace_service.bootstrap_workspace_session(db, request, response)
