from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class TranslatedError(BaseModel):
    code: str
    title: str
    message: str
    next_action: dict[str, str]


class LLMStatus(BaseModel):
    configured: bool = False
    available: bool = False
    provider: str = ""
    model: str = ""
    label: str = ""
    runtime_configurable: bool = False
    key_storage: str = "local_file"
    auto_detected: str = ""
    error: TranslatedError | None = None


class OllamaDetectResult(BaseModel):
    detected: bool = False
    models: list[str] = Field(default_factory=list)
    recommended_model: str = ""


class LocalAIServer(BaseModel):
    """A detected local AI server."""
    port: int
    base_url: str
    model: str = ""
    models: list[str] = Field(default_factory=list)
    label: str = ""


class LocalAIDetectResult(BaseModel):
    servers: list[LocalAIServer] = Field(default_factory=list)


class LLMTestResult(BaseModel):
    success: bool
    provider: str = ""
    model: str = ""
    message: str = ""


class ProviderPreset(BaseModel):
    name: str
    label: str
    base_url: str
    model: str
    needs_api_key: bool = False
    internal: bool = False


class ProfileSummary(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    target_roles_count: int = 0
    locations: list[str] = []


class ProfileDetail(BaseModel):
    name: str
    config: dict = {}


class ProfilePreferences(BaseModel):
    """User-editable profile preferences (subset of full profile config)."""
    preferred_locations: list[str] = Field(default_factory=list)
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    max_days_old: int = 14
    current_title: str = ""
    current_level: str = "mid"
    current_tc: int = 100_000
    min_base: int = 80_000
    target_total_comp: int = 150_000
    auto_apply_enabled: bool = False
    auto_apply_dry_run: bool = True

    # Scoring weights
    scoring_technical: float = 0.25
    scoring_leadership: float = 0.15
    scoring_career_progression: float = 0.15
    scoring_platform: float = 0.13
    scoring_comp: float = 0.12
    scoring_trajectory: float = 0.10
    scoring_culture: float = 0.10

    # Thresholds
    threshold_strong_apply: int = 70
    threshold_apply: int = 55
    threshold_maybe: int = 40

    # Toggles
    exclude_staffing_agencies: bool = True
    include_equity: bool = True

    # Career
    min_acceptable_tc: float | None = None

class ProfilePreferencesResponse(BaseModel):
    name: str
    preferences: ProfilePreferences


class FetchModelsRequest(BaseModel):
    base_url: str
    api_key: str = ""


class ProviderModel(BaseModel):
    id: str
    name: str = ""


class DatabaseInfo(BaseModel):
    path: str = ""
    exists: bool = False
    size_mb: float = 0.0
    record_count: int = 0
