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


class KitRequest(BaseModel):
    cover_letter: str | None = None  # User-edited version, saved before the kit builds


class KitResponse(BaseModel):
    """The application kit: everything prefilled, the human sends it.

    Questboard never transmits an application (docs/anti-slop.md).
    """
    success: bool
    method: str | None = None  # "greenhouse", "lever", "linkedin", None
    message: str
    # where the human acts
    apply_url: str = ""
    # the ATS form, prefilled (empty for unmapped ATS types)
    fields: dict = {}
