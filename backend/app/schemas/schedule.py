"""Pydantic schemas for the schedule API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScheduleUpdate(BaseModel):
    enabled: bool = False
    interval_hours: float = Field(default=6.0, ge=1.0, le=168.0)
    mode: str = "search_score"


class ScheduleResponse(BaseModel):
    profile: str
    enabled: bool = False
    interval_hours: float = 6.0
    mode: str = "search_score"
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_run_jobs_found: int = 0
    last_run_new_jobs: int = 0

    model_config = {"from_attributes": True}
