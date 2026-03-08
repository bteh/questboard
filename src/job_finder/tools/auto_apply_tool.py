"""Auto-apply tools for Greenhouse, Lever, and LinkedIn job submissions.

All auto-apply features are OPT-IN and require explicit configuration.
LinkedIn Easy Apply is flagged for manual follow-up only (no public API).
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import Any

import requests

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


# -- Greenhouse Submission ---------------------------------------------------


def submit_greenhouse_application(
    board_token: str,
    job_id: str,
    application_data: dict,
    api_key: str = "",
) -> dict:
    """Submit application via Greenhouse Job Board API.

    ``POST https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}``

    Returns ``{"success": bool, "message": str, "response": dict|None}``.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"

    data: dict[str, Any] = {
        "first_name": application_data["first_name"],
        "last_name": application_data["last_name"],
        "email": application_data["email"],
    }
    if application_data.get("phone"):
        data["phone"] = application_data["phone"]

    cover_letter = application_data.get("cover_letter_text", "")
    if cover_letter:
        data["cover_letter"] = cover_letter

    files: dict[str, Any] = {}
    resume_path = application_data.get("resume_path", "")
    if resume_path and os.path.exists(resume_path):
        files["resume"] = (
            os.path.basename(resume_path),
            open(resume_path, "rb"),
            "application/pdf",
        )

    try:
        headers: dict[str, str] = {}
        if api_key:
            encoded = base64.b64encode(f"{api_key}:".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        resp = requests.post(
            url, data=data, files=files, headers=headers, timeout=30,
        )

        if resp.status_code in (200, 201):
            return {
                "success": True,
                "message": "Application submitted via Greenhouse",
                "response": resp.json(),
            }
        else:
            return {
                "success": False,
                "message": f"Greenhouse HTTP {resp.status_code}: {resp.text[:500]}",
                "response": None,
            }
    except Exception as e:
        return {"success": False, "message": str(e), "response": None}
    finally:
        for f in files.values():
            if hasattr(f[1], "close"):
                f[1].close()


# -- Lever Submission --------------------------------------------------------


def submit_lever_application(
    company: str,
    posting_id: str,
    application_data: dict,
) -> dict:
    """Submit application via Lever Postings API.

    ``POST https://jobs.lever.co/v0/postings/{company}/{posting_id}``

    Returns ``{"success": bool, "message": str, "response": dict|None}``.
    """
    url = f"https://jobs.lever.co/v0/postings/{company}/{posting_id}"

    data: dict[str, Any] = {
        "name": f"{application_data['first_name']} {application_data['last_name']}",
        "email": application_data["email"],
    }
    if application_data.get("phone"):
        data["phone"] = application_data["phone"]
    if application_data.get("linkedin_url"):
        data["urls[LinkedIn]"] = application_data["linkedin_url"]

    cover_letter = application_data.get("cover_letter_text", "")
    if cover_letter:
        data["comments"] = cover_letter

    files: dict[str, Any] = {}
    resume_path = application_data.get("resume_path", "")
    if resume_path and os.path.exists(resume_path):
        files["resume"] = (
            os.path.basename(resume_path),
            open(resume_path, "rb"),
            "application/pdf",
        )

    try:
        resp = requests.post(url, data=data, files=files, timeout=30)

        if resp.status_code == 200:
            body = resp.json()
            if body.get("ok"):
                return {
                    "success": True,
                    "message": "Application submitted via Lever",
                    "response": body,
                }
            else:
                return {
                    "success": False,
                    "message": f"Lever rejected: {body}",
                    "response": body,
                }
        else:
            return {
                "success": False,
                "message": f"Lever HTTP {resp.status_code}: {resp.text[:500]}",
                "response": None,
            }
    except Exception as e:
        return {"success": False, "message": str(e), "response": None}
    finally:
        for f in files.values():
            if hasattr(f[1], "close"):
                f[1].close()


# -- Unified Apply Function --------------------------------------------------


def auto_apply(
    job: dict,
    config: dict,
    resume_path: str = "",
    cover_letter_text: str = "",
    dry_run: bool = True,
) -> dict:
    """Attempt to auto-apply to a job via detected ATS.

    Parameters
    ----------
    dry_run : bool
        If ``True``, prepare the application but don't actually submit.

    Returns
    -------
    dict
        Keys: ``method``, ``success``, ``message``, and optionally
        ``application_data`` (dry run) or ``response`` (live).
    """
    # Check for ATS URL override (e.g. from YC scraper detail pages)
    job_url = job.get("ats_url") or job.get("url", "")
    ats_type = job.get("ats_type") or detect_ats_type(job_url)

    if not ats_type:
        return {"method": None, "success": False, "message": "Unknown ATS type"}

    # Check if this ATS method is enabled
    methods_config = config.get("auto_apply", {}).get("methods", {})
    if ats_type == "greenhouse" and not methods_config.get("greenhouse", True):
        return {"method": "greenhouse", "success": False, "message": "Greenhouse disabled in config"}
    if ats_type == "lever" and not methods_config.get("lever", True):
        return {"method": "lever", "success": False, "message": "Lever disabled in config"}

    app_data = build_application_data(config, job, resume_path, cover_letter_text)

    # Validate required fields
    if not app_data["email"] or not app_data["first_name"]:
        return {
            "method": ats_type,
            "success": False,
            "message": "Missing applicant_info in config (need at least first_name and email)",
        }

    if dry_run:
        return {
            "method": ats_type,
            "success": True,
            "message": f"Dry run: would submit to {ats_type} for {job.get('company', '')}",
            "application_data": app_data,
        }

    if ats_type == "greenhouse":
        ids = extract_greenhouse_ids(job_url)
        if not ids:
            return {
                "method": "greenhouse",
                "success": False,
                "message": "Could not extract Greenhouse IDs from URL",
            }
        board_token, job_id = ids
        api_key = config.get("greenhouse_api_key", "")
        result = submit_greenhouse_application(board_token, job_id, app_data, api_key)
        result["method"] = "greenhouse"
        return result

    elif ats_type == "lever":
        ids = extract_lever_posting_id(job_url)
        if not ids:
            return {
                "method": "lever",
                "success": False,
                "message": "Could not extract Lever posting ID from URL",
            }
        company, posting_id = ids
        result = submit_lever_application(company, posting_id, app_data)
        result["method"] = "lever"
        return result

    elif ats_type == "linkedin":
        return {
            "method": "linkedin",
            "success": False,
            "message": (
                "LinkedIn Easy Apply requires manual submission. "
                "Materials have been prepared — apply at: " + job_url
            ),
            "application_data": app_data,
        }

    return {"method": ats_type, "success": False, "message": "Unsupported ATS"}
