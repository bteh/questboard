from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.analytics import ChartDataPoint, DashboardStats
from app.services import analytics_service, workspace_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(request: Request, profile: str | None = None, db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_dashboard_stats(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
    )


@router.get("/score-distribution", response_model=list[ChartDataPoint])
def get_score_distribution(request: Request, profile: str | None = None, db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_score_distribution(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
    )


@router.get("/recommendations", response_model=list[ChartDataPoint])
def get_recommendations(request: Request, profile: str | None = None, db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_recommendation_breakdown(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
    )


@router.get("/sources", response_model=list[ChartDataPoint])
def get_sources(request: Request, profile: str | None = None, db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_source_breakdown(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
    )


@router.get("/funnel", response_model=list[ChartDataPoint])
def get_funnel(request: Request, profile: str | None = None, db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_pipeline_funnel(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
    )


@router.get("/top-companies")
def get_top_companies(request: Request, limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_top_companies(
        db,
        limit=limit,
        workspace_id=workspace.workspace.id if workspace else None,
    )


@router.get("/company-types")
def get_company_types(request: Request, db: Session = Depends(get_db)):
    workspace = workspace_service.get_workspace_context_optional(db, request)
    return analytics_service.get_company_types(
        db,
        workspace_id=workspace.workspace.id if workspace else None,
    )
