from __future__ import annotations

from pydantic import BaseModel


class PrepareResponse(BaseModel):
    ats_type: str | None = None  # "greenhouse", "lever", None
    ats_detected: bool
    cover_letter: str | None = None
    resume_tweaks: dict | None = None
    applicant_info: dict  # { first_name, last_name, email, phone }
    job_title: str
    company: str
    job_url: str


class SubmitRequest(BaseModel):
    cover_letter: str | None = None  # User-edited version
    dry_run: bool = True


class SubmitResponse(BaseModel):
    success: bool
    method: str | None = None  # "greenhouse", "lever", None
    message: str
    dry_run: bool
