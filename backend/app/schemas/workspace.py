from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceSessionResponse(BaseModel):
    workspace_id: str
    expires_at: datetime
    hosted_mode: bool = True
    csrf_required: bool = True
    llm_optional: bool = True


class PlaceSelection(BaseModel):
    label: str
    kind: Literal["city", "region", "country", "manual"] = "manual"
    city: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""
    lat: float | None = None
    lon: float | None = None
    provider: str = "manual"
    provider_id: str = ""


class CompensationPreference(BaseModel):
    currency: str = "USD"
    pay_period: Literal["hourly", "monthly", "annual"] = "annual"
    current_comp: float | None = None
    min_base: float | None = None
    target_total_comp: float | None = None
    min_acceptable_tc: float | None = None
    include_equity: bool = True


class WorkspacePreferences(BaseModel):
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    preferred_places: list[PlaceSelection] = Field(default_factory=list)
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    max_days_old: int = 14
    current_title: str = ""
    current_level: str = "mid"
    compensation: CompensationPreference = Field(default_factory=CompensationPreference)
    exclude_staffing_agencies: bool = True


class WorkspaceResumeStatus(BaseModel):
    exists: bool = False
    filename: str = ""
    file_size: int = 0
    parse_status: Literal["missing", "parsed", "warning", "error"] = "missing"
    parse_warning: str = ""


class OnboardingState(BaseModel):
    workspace_id: str
    needs_resume: bool = True
    needs_preferences: bool = True
    ready_to_search: bool = False
    resume_warning: str = ""
    llm_optional: bool = True
    llm_available: bool = False
    resume: WorkspaceResumeStatus = Field(default_factory=WorkspaceResumeStatus)
    preferences: WorkspacePreferences = Field(default_factory=WorkspacePreferences)


class WorkspaceResumeUploadResponse(BaseModel):
    message: str = "Resume uploaded successfully"
    resume: WorkspaceResumeStatus
    analysis: dict | None = None


class LocationSuggestion(BaseModel):
    label: str
    kind: Literal["city", "region", "country", "manual"] = "manual"
    subtitle: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""
    lat: float | None = None
    lon: float | None = None
    provider: str = "manual"
    provider_id: str = ""


class SearchSnapshot(BaseModel):
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    preferred_places: list[PlaceSelection] = Field(default_factory=list)
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    max_days_old: int = 14
    current_title: str = ""
    current_level: str = ""
    compensation: CompensationPreference = Field(default_factory=CompensationPreference)
    exclude_staffing_agencies: bool = True


class WorkspaceSearchRunResponse(BaseModel):
    run_id: str
    status: Literal["pending", "running", "completed", "failed"]
    started_at: datetime | None = None
    completed_at: datetime | None = None

