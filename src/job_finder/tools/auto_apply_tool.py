"""The application kit: everything prefilled, the human sends it.

Questboard never transmits an application. On the receiving end a POST
from our servers is indistinguishable from spray-and-pray no matter how
carefully it is capped, and employers are writing AI-use policies against
exactly that shape (the 2026-07-10 strategy debate, unanimous;
docs/anti-slop.md is the published stance). What earns a landing is
judgment and readiness, so this module keeps all of that: ATS route
detection, the per-ATS form field maps, and kit assembly. The one thing
it no longer contains is a code path that fires the request; the
requests import left with it.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)


# -- ATS Detection ---------------------------------------------------------


def detect_ats_type(job_url: str) -> str | None:
    """Detect ATS type from job URL pattern.

    Returns ``"greenhouse"``, ``"lever"``, ``"linkedin"``, or ``None``.
    """
    url_lower = job_url.lower()
    if "greenhouse.io" in url_lower:
        return "greenhouse"
    if "lever.co" in url_lower:
        return "lever"
    if "linkedin.com" in url_lower:
        return "linkedin"
    return None


def extract_greenhouse_ids(job_url: str) -> tuple[str, str] | None:
    """Extract board_token and job_id from a Greenhouse URL.

    URL patterns:
    - ``boards.greenhouse.io/company/jobs/123456``
    - ``company.greenhouse.io/jobs/123456``
    """
    patterns = [
        r'boards\.greenhouse\.io/([^/]+)/jobs/(\d+)',
        r'([^./]+)\.greenhouse\.io/jobs/(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, job_url)
        if match:
            return match.group(1), match.group(2)
    return None


def extract_lever_posting_id(job_url: str) -> tuple[str, str] | None:
    """Extract company and posting ID from a Lever URL.

    URL pattern: ``jobs.lever.co/company/posting-uuid``
    """
    match = re.search(r'jobs\.lever\.co/([^/]+)/([a-f0-9-]+)', job_url)
    if match:
        return match.group(1), match.group(2)
    return None


# -- Application Data Builder -----------------------------------------------


def build_application_data(
    config: dict,
    job: dict,
    resume_path: str = "",
    cover_letter_text: str = "",
) -> dict:
    """Build the standard application payload from config + job data."""
    applicant = config.get("applicant_info", {})
    return {
        "first_name": applicant.get("first_name", ""),
        "last_name": applicant.get("last_name", ""),
        "email": applicant.get("email", ""),
        "phone": applicant.get("phone", ""),
        "linkedin_url": applicant.get("linkedin_url", ""),
        "resume_path": resume_path,
        "cover_letter_text": cover_letter_text,
        "job_url": job.get("url", ""),
        "job_title": job.get("title", ""),
        "company": job.get("company", ""),
    }


# -- Field maps (the form-mapping knowledge, kept as data) -------------------


def greenhouse_field_map(application_data: dict) -> dict:
    """The fields a Greenhouse application form takes, prefilled.

    This is the same mapping the deleted submission path used to POST;
    it now exists so a human can fill the real form in seconds.
    """
    fields = {
        "first_name": application_data.get("first_name", ""),
        "last_name": application_data.get("last_name", ""),
        "email": application_data.get("email", ""),
    }
    if application_data.get("phone"):
        fields["phone"] = application_data["phone"]
    if application_data.get("cover_letter_text"):
        fields["cover_letter"] = application_data["cover_letter_text"]
    resume_path = application_data.get("resume_path", "")
    if resume_path and os.path.exists(resume_path):
        fields["resume"] = resume_path
    return fields


def lever_field_map(application_data: dict) -> dict:
    """The fields a Lever posting form takes, prefilled."""
    first = application_data.get("first_name", "")
    last = application_data.get("last_name", "")
    fields = {
        "name": f"{first} {last}".strip(),
        "email": application_data.get("email", ""),
    }
    if application_data.get("phone"):
        fields["phone"] = application_data["phone"]
    if application_data.get("linkedin_url"):
        fields["urls[LinkedIn]"] = application_data["linkedin_url"]
    if application_data.get("cover_letter_text"):
        fields["comments"] = application_data["cover_letter_text"]
    resume_path = application_data.get("resume_path", "")
    if resume_path and os.path.exists(resume_path):
        fields["resume"] = resume_path
    return fields


# -- The kit ------------------------------------------------------------------


def prepare_application_kit(
    job: dict,
    config: dict,
    resume_path: str = "",
    cover_letter_text: str = "",
) -> dict:
    """Everything prefilled for the detected ATS; the human sends it.

    Returns ``method``, ``success``, ``message``, ``apply_url`` (where the
    human acts), ``fields`` (the ATS form, prefilled), and
    ``application_data`` (the raw payload the fields derive from).
    """
    job_url = job.get("ats_url") or job.get("url", "")
    ats_type = job.get("ats_type") or detect_ats_type(job_url)

    if not ats_type:
        return {"method": None, "success": False, "message": "Unknown ATS type"}

    app_data = build_application_data(config, job, resume_path, cover_letter_text)
    if not app_data["email"] or not app_data["first_name"]:
        return {
            "method": ats_type,
            "success": False,
            "message": "Missing applicant_info in config (need at least first_name and email)",
        }

    if ats_type == "greenhouse":
        fields = greenhouse_field_map(app_data)
    elif ats_type == "lever":
        fields = lever_field_map(app_data)
    else:
        # LinkedIn Easy Apply and anything unmapped: the kit still carries
        # the materials, the form mapping is theirs to render
        fields = {}

    company = job.get("company", "")
    return {
        "method": ats_type,
        "success": True,
        "message": f"Kit ready for {company or 'this posting'} via {ats_type}; you send it",
        "apply_url": job_url,
        "fields": fields,
        "application_data": app_data,
    }
