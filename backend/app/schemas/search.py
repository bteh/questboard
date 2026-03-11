from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    include_remote: bool = True
    max_days_old: int = 14
    use_ai: bool = False
    profile: str = "default"
    mode: str = Field(
        default="search_score",
        description="search_only | search_score | full_pipeline",
    )


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
    keywords: list[str] = Field(default_factory=list)
    max_days_old: int = 14
    profile: str = "default"


class SearchSuggestions(BaseModel):
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    summary: str = ""
