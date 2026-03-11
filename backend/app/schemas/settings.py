from __future__ import annotations

from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class LLMStatus(BaseModel):
    configured: bool = False
    available: bool = False
    provider: str = ""
    model: str = ""
    label: str = ""


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
    current_title: str = ""
    current_level: list[str] = ["mid"]
    current_tc: int = 100_000
    min_base: int = 80_000
    target_total_comp: int = 150_000

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


