from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.analytics import ChartDataPoint, DashboardStats
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(profile: str | None = None, db: Session = Depends(get_db)):
    return analytics_service.get_dashboard_stats(db, profile=profile)


@router.get("/score-distribution", response_model=list[ChartDataPoint])
def get_score_distribution(profile: str | None = None, db: Session = Depends(get_db)):
    return analytics_service.get_score_distribution(db, profile=profile)


@router.get("/recommendations", response_model=list[ChartDataPoint])
def get_recommendations(profile: str | None = None, db: Session = Depends(get_db)):
    return analytics_service.get_recommendation_breakdown(db, profile=profile)


@router.get("/sources", response_model=list[ChartDataPoint])
def get_sources(profile: str | None = None, db: Session = Depends(get_db)):
    return analytics_service.get_source_breakdown(db, profile=profile)


@router.get("/funnel", response_model=list[ChartDataPoint])
def get_funnel(profile: str | None = None, db: Session = Depends(get_db)):
    return analytics_service.get_pipeline_funnel(db, profile=profile)


@router.get("/top-companies")
def get_top_companies(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    return analytics_service.get_top_companies(db, limit=limit)


@router.get("/company-types")
def get_company_types(db: Session = Depends(get_db)):
    return analytics_service.get_company_types(db)
