from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ApplicationBase(BaseModel):
    job_title: str
    company: str
    location: str = ""
    job_url: str = ""
    source: str = ""
    description: str = ""
    is_remote: bool = False
    work_type: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""
    salary_min_annualized: float | None = None
    salary_max_annualized: float | None = None
    # Provenance/confidence contract fields (mirrored by the frontend types):
    # salary_source: 'reported' | 'parsed_from_description' | None
    # date_confidence: 'exact' | 'fuzzy' | 'missing' | None
    # work_type_confidence: 'reported' | 'inferred' | None
    salary_source: str | None = None
    date_confidence: str | None = None
    work_type_confidence: str | None = None
    # Trust & freshness (ghost-job defense). date_posted is the job's TRUE
    # original post date (raw source string); the UI derives real age from it.
    # direct_from_company is True when the source links straight to the
    # employer's own ATS/board (Greenhouse, Lever, Ashby, Workable, ...).
    date_posted: str | None = None
    direct_from_company: bool = False


class ApplicationResponse(ApplicationBase):
    id: int
    # Quest verticals. vertical matches packages/ui/src/tokens.ts
    # (career|camera|study|lens|party); every field defaults to the career
    # shape so existing consumers deserialize unchanged.
    vertical: str = "career"
    event_start: datetime | None = None
    event_end: datetime | None = None
    is_rolling: bool = False
    first_quest_ok: bool = False
    quest_json: str = ""
    # quest_json parsed for card rendering; None when absent or unparseable.
    quest: dict | None = None
    overall_score: float | None = None
    technical_score: float | None = None
    leadership_score: float | None = None
    platform_building_score: float | None = None
    comp_potential_score: float | None = None
    company_trajectory_score: float | None = None
    culture_fit_score: float | None = None
    career_progression_score: float | None = None
    recommendation: str = ""
    score_reasoning: str = ""
    key_strengths: list[str] = []
    key_gaps: list[str] = []
    # Per-dimension keyword evidence:
    # {<dimension>: {"matched": [...], "missing_top": [...]}}
    score_evidence: dict[str, dict] | None = None
    funding_stage: str | None = None
    total_funding: str | None = None
    employee_count: str | None = None
    company_type: str = ""
    company_intel_json: str = ""
    resume_tweaks_json: str = ""
    evaluation_report_json: str = ""
    cover_letter: str = ""
    application_method: str = ""
    profile: str = "default"
    status: str = "found"
    date_found: datetime | None = None
    date_applied: datetime | None = None
    notes: str = ""
    contact_name: str = ""
    contact_email: str = ""
    referral_source: str = ""
    url_status: str = "unknown"
    last_checked_at: datetime | None = None
    user_feedback: str = ""
    feedback_notes: str = ""
    # Tags the run that last surfaced this job (overwritten on each rediscovery).
    search_run_id: str | None = None
    # Tags the run that originally found this job (set once, never overwritten).
    # The UI uses this to mark truly-new jobs in the latest run vs jobs that
    # earlier runs already surfaced.
    first_seen_run_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    page: int = 1
    page_size: int = 25


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    referral_source: str | None = None
    # The log writes user-entered quest facts here, e.g. {"paid_out": 45}
    # when a quest is marked done with a real paid figure. Must be a JSON
    # object; the value is stored verbatim and never inferred server-side.
    quest_json: str | None = None

    @field_validator("quest_json")
    @classmethod
    def _quest_json_is_object(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import json

        try:
            parsed = json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError("quest_json must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("quest_json must be a JSON object")
        return v


class StatusUpdate(BaseModel):
    # One shared lifecycle, widened additively for quests. 'clipped' is the
    # real saved/shortlisted status (the board used to overload 'reviewed',
    # which stays valid); booked/attended/paid_out/expired cover the quest
    # lifecycle; 'shelved' is the log's put-aside state (reopen restores it).
    # Every pre-existing value stays valid.
    status: Literal[
        "found", "reviewed", "clipped", "applying", "applied", "interviewing",
        "offer", "rejected", "withdrawn", "shelved",
        "booked", "attended", "paid_out", "expired",
    ]
    notes: str | None = None


class FeedbackUpdate(BaseModel):
    """Quick thumbs up/down signal from job cards."""

    feedback: Literal["up", "down", ""]
    notes: str | None = None


class ApplicationCreate(BaseModel):
    job_title: str
    company: str = ""
    location: str = ""
    job_url: str = ""
    source: str = "manual"
    description: str = ""
    is_remote: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    status: str = "found"
    notes: str = ""
    profile: str = "default"
    # Which lane the row belongs to. The log's composer writes 'personal'
    # (source 'user', no URL); everything else defaults to career. Validated
    # against APPLICATION_VERTICALS on save.
    vertical: str = "career"
