from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.workspace import PlaceSelection


class SearchRequest(BaseModel):
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    preferred_places: list[PlaceSelection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    include_remote: bool = True
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    max_days_old: int = 14
    include_linkedin_jobs: bool = False
    use_ai: bool = False
    profile: str = "default"
    mode: Literal["search_only", "search_score", "full_pipeline"] = Field(
        default="search_score",
        description="search_only | search_score | full_pipeline",
    )

    @field_validator("profile")
    @classmethod
    def _validate_profile(cls, value: str) -> str:
        if not value:
            return "default"
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "profile must contain only alphanumeric characters, hyphens, and underscores"
            )
        return value


class RunStatus(BaseModel):
    run_id: str
    status: str  # pending | running | completed | failed
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress_messages: list[str] = Field(default_factory=list)
    jobs_found: int = 0
    jobs_scored: int = 0
    error: str | None = None


class RunResult(BaseModel):
    run_id: str
    status: str
    jobs_found: int = 0
    jobs_scored: int = 0
    strong_matches: int = 0
    duration_seconds: float = 0.0
    error: str | None = None


class SearchDefaults(BaseModel):
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    preferred_places: list[PlaceSelection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    include_remote: bool = True
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    max_days_old: int = 14
    include_linkedin_jobs: bool = False
    profile: str = "default"
    current_title: str = ""
    current_level: str = ""
    current_tc: float | None = None
    min_base: float | None = None
    target_total_comp: float | None = None
    min_acceptable_tc: float | None = None
    compensation_currency: str = "USD"
    compensation_period: Literal["hourly", "monthly", "annual"] = "annual"
    exclude_staffing_agencies: bool = True


class SearchSuggestions(BaseModel):
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    summary: str = ""
