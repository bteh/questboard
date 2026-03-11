from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.analytics import ChartDataPoint, DashboardStats
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    return analytics_service.get_dashboard_stats(db)


@router.get("/score-distribution", response_model=list[ChartDataPoint])
def get_score_distribution(db: Session = Depends(get_db)):
    return analytics_service.get_score_distribution(db)


@router.get("/recommendations", response_model=list[ChartDataPoint])
def get_recommendations(db: Session = Depends(get_db)):
    return analytics_service.get_recommendation_breakdown(db)


@router.get("/sources", response_model=list[ChartDataPoint])
def get_sources(db: Session = Depends(get_db)):
    return analytics_service.get_source_breakdown(db)


@router.get("/funnel", response_model=list[ChartDataPoint])
def get_funnel(db: Session = Depends(get_db)):
    return analytics_service.get_pipeline_funnel(db)


@router.get("/top-companies")
def get_top_companies(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    return analytics_service.get_top_companies(db, limit=limit)


@router.get("/company-types")
def get_company_types(db: Session = Depends(get_db)):
    return analytics_service.get_company_types(db)
