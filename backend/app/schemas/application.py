from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApplicationBase(BaseModel):
    job_title: str
    company: str
    location: str = ""
    job_url: str = ""
    source: str = ""
    description: str = ""
    is_remote: bool = False
    work_type: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""
    salary_min_annualized: float | None = None
    salary_max_annualized: float | None = None


class ApplicationResponse(ApplicationBase):
    id: int
    overall_score: float | None = None
    technical_score: float | None = None
    leadership_score: float | None = None
    platform_building_score: float | None = None
    comp_potential_score: float | None = None
    company_trajectory_score: float | None = None
    culture_fit_score: float | None = None
    career_progression_score: float | None = None
    recommendation: str = ""
    score_reasoning: str = ""
    key_strengths: list[str] = []
    key_gaps: list[str] = []
    funding_stage: str | None = None
    total_funding: str | None = None
    employee_count: str | None = None
    company_type: str = ""
    company_intel_json: str = ""
    resume_tweaks_json: str = ""
    cover_letter: str = ""
    application_method: str = ""
    profile: str = "default"
    status: str = "found"
    date_found: datetime | None = None
    date_applied: datetime | None = None
    notes: str = ""
    contact_name: str = ""
    contact_email: str = ""
    referral_source: str = ""
    url_status: str = "unknown"
    last_checked_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int = 1
    page_size: int = 25


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    referral_source: str | None = None


class StatusUpdate(BaseModel):
    status: Literal["found", "reviewed", "applying", "applied", "interviewing", "offer", "rejected", "withdrawn"]
    notes: str | None = None


class ApplicationCreate(BaseModel):
    job_title: str
    company: str
    location: str = ""
    job_url: str = ""
    source: str = "manual"
    description: str = ""
    is_remote: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    status: str = "found"
    notes: str = ""
    profile: str = "default"
