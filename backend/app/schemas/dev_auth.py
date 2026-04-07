from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DevHostedPersonaSummary(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: str = ""
    headline: str
    background: str
    job_search_focus: str
    current_title: str = ""
    current_level: str = "mid"
    target_roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    preferred_places: list[str] = Field(default_factory=list)
    workplace_preference: Literal["remote_friendly", "remote_only", "location_only"] = "remote_friendly"
    resume_filename: str


class DevHostedLoginRequest(BaseModel):
    persona_id: str
    reset: bool = False


class DevHostedLoginResponse(BaseModel):
  access_token: str
  token_type: Literal["bearer"] = "bearer"
  expires_at: datetime
  persona: DevHostedPersonaSummary


class DevHostedRegisterRequest(BaseModel):
    email: str
    full_name: str
    reset: bool = False


class DevHostedUserSummary(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: str = ""
    auth_provider: str = "dev-sandbox"
    seeded: bool = False


class DevHostedRegisterResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: DevHostedUserSummary
