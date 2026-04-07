from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies import get_active_workspace_context
from app.models.database import get_db
from app.schemas.analytics import ChartDataPoint, DashboardStats
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    profile: str | None = None,
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_dashboard_stats(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )


@router.get("/score-distribution", response_model=list[ChartDataPoint])
def get_score_distribution(
    profile: str | None = None,
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_score_distribution(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )


@router.get("/recommendations", response_model=list[ChartDataPoint])
def get_recommendations(
    profile: str | None = None,
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_recommendation_breakdown(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )


@router.get("/sources", response_model=list[ChartDataPoint])
def get_sources(
    profile: str | None = None,
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_source_breakdown(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )


@router.get("/funnel", response_model=list[ChartDataPoint])
def get_funnel(
    profile: str | None = None,
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_pipeline_funnel(
        db,
        profile=None if workspace else profile,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )


@router.get("/top-companies")
def get_top_companies(
    limit: int = Query(10, ge=1, le=50),
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_top_companies(
        db,
        limit=limit,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )


@router.get("/company-types")
def get_company_types(
    search_run_id: str | None = None,
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    return analytics_service.get_company_types(
        db,
        workspace_id=workspace.workspace.id if workspace else None,
        search_run_id=search_run_id,
    )
