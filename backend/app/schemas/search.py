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
    max_days_old: int = 30
    # LinkedIn on by default — a second working board for circuit-breaker
    # redundancy. The client can still send False to opt out per run.
    include_linkedin_jobs: bool = True
    use_ai: bool = False
    profile: str = "default"
    mode: Literal["search_only", "search_score", "full_pipeline"] = Field(
        default="search_score",
        description="search_only | search_score | full_pipeline",
    )
    # Per-run override for filter strictness. None = inherit saved default
    # (WorkspacePreferences.match_strictness).
    match_strictness: Literal["loose", "balanced", "strict"] | None = None

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


class SourceCoverageItem(BaseModel):
    source: str
    display_name: str
    state: Literal["ok", "zero", "partial", "failed"]
    rows_found: int = 0
    attempts: int = 0
    failed_attempts: int = 0
    error: str = ""

class SourceCoverage(BaseModel):
    total: int = 0
    ok: int = 0
    zero: int = 0
    partial: int = 0
    failed: int = 0
    sources: list[SourceCoverageItem] = Field(default_factory=list)


class RunStatus(BaseModel):
    run_id: str
    status: str  # pending | running | completed | failed
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress_messages: list[str] = Field(default_factory=list)
    jobs_found: int = 0
    new_jobs: int = 0
    jobs_scored: int = 0
    error: str | None = None
    source_coverage: SourceCoverage | None = None


class RunResult(BaseModel):
    run_id: str
    status: str
    jobs_found: int = 0
    new_jobs: int = 0
    jobs_scored: int = 0
    strong_matches: int = 0
    duration_seconds: float = 0.0
    error: str | None = None
    source_coverage: SourceCoverage | None = None


class FunnelStage(BaseModel):
    key: str
    label: str
    count_in: int
    count_out: int
    dropped: int
    active: bool = True


class FunnelSummary(BaseModel):
    run_id: str | None = None
    status: str = "completed"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    raw_count: int = 0
    final_count: int = 0
    stages: list[FunnelStage] = Field(default_factory=list)


class SearchDefaults(BaseModel):
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    preferred_places: list[PlaceSelection] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    include_remote: bool = True
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    max_days_old: int = 30
    include_linkedin_jobs: bool = True
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
    match_strictness: Literal["loose", "balanced", "strict"] = "balanced"


class SearchSuggestions(BaseModel):
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    summary: str = ""
    ai_failed: bool = False
