"""Location suggestion API for hosted search/preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import get_workspace_context
from app.models.database import get_db
from app.schemas.workspace import LocationSuggestion
from app.security import enforce_rate_limit, request_identity
from app.services import location_service

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("/suggest", response_model=list[LocationSuggestion])
def suggest_locations(
    request: Request,
    q: str = Query("", min_length=2, max_length=100),
    limit: int = Query(8, ge=1, le=10),
    context = Depends(get_workspace_context),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    enforce_rate_limit(
        "location-suggest",
        request_identity(request, context.workspace.id),
        limit=settings.location_rate_limit_per_minute,
        db=db,
    )
    return location_service.suggest_locations(q, limit=limit)
