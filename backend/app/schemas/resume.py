from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeStatus(BaseModel):
    profile: str
    exists: bool = False
    filename: str = ""
    file_size: int = 0
    path: str = ""


class AgentConsentStatus(BaseModel):
    """Whether the connected agent may read the local resume."""

    granted: bool = False
    granted_at: str | None = None
    expires_at: str | None = None


class AgentConsentRequest(BaseModel):
    grant: bool
    ttl_hours: int | None = None


class ResumeAnalysisSummary(BaseModel):
    """Summary of what resume analysis extracted, echoed in the upload response."""

    skills: list[str] = Field(default_factory=list)
    suggested_target_roles: list[str] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
    current_title: str = ""
    seniority: str = ""
    certifications: list[str] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    profile: str
    filename: str
    message: str = "Resume uploaded successfully"
    parse_status: str = "ok"  # "ok" | "error"
    parse_code: str | None = None  # "SCANNED_PDF" | None
    analysis_status: str = "skipped_no_llm"  # "completed" | "skipped_no_llm" | "analysis_error" | "failed"
    analysis: ResumeAnalysisSummary | None = None
