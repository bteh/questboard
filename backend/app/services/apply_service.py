"""Auto-apply service -- prepare application materials and submit via ATS."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.dependencies import get_config, get_llm
from app.models.application import ApplicationRecord

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def prepare_application(
    db: Session,
    app_id: int,
    profile: str = "default",
    workspace_id: str | None = None,
) -> dict | None:
    """Load an application record and prepare materials for submission.

    Detects the ATS type from the job URL, generates a cover letter and
    resume tweaks via the pipeline when they are missing, and persists
    the generated materials back to the DB.

    Returns a dict matching ``PrepareResponse``, or *None* when the
    application record cannot be found.
    """
    from job_finder.tools.auto_apply_tool import detect_ats_type
    from job_finder.tools.resume_parser_tool import parse_resume
    from job_finder.pipeline import JobFinderPipeline

    record = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id).first()
    if not record:
        return None

    config = get_config(profile)
    job_url = record.job_url or ""

    # ATS detection
    ats_type = detect_ats_type(job_url) if job_url else None

    # Resume text -- workspace-aware to prevent cross-user data leaks
    if workspace_id:
        from app.services import workspace_service
        resume_text = workspace_service.get_resume_text(db, workspace_id)
        if not resume_text:
            resume_text = "ERROR: No resume uploaded. Please upload your resume in Settings."
    else:
        resume_text = parse_resume(profile=profile)
    has_resume = not resume_text.startswith("ERROR")

    # Build a job dict that the pipeline methods expect
    job = {
        "title": record.job_title,
        "company": record.company,
        "location": record.location or "",
        "description": record.description or "",
        "url": job_url,
        "overall_score": record.overall_score,
        "key_strengths": record.strengths_list,
        "key_gaps": record.gaps_list,
    }

    # LLM-powered generation (gracefully degrades when LLM is unavailable)
    llm = get_llm()
    pipeline = JobFinderPipeline(
        llm=llm if llm.is_configured else None,
        profile=profile,
    )

    cover_letter = record.cover_letter or None
    resume_tweaks: dict | None = None

    # Parse existing resume tweaks JSON if present
    if record.resume_tweaks_json:
        try:
            resume_tweaks = json.loads(record.resume_tweaks_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Generate cover letter if missing and we have a resume
    if not cover_letter and has_resume:
        cl_result = pipeline.write_cover_letter(job, resume_text)
        if cl_result:
            cover_letter = cl_result.get("cover_letter_text", "")
            if cover_letter:
                record.cover_letter = cover_letter
                logger.info(
                    "Generated cover letter for app %d (%s @ %s)",
                    app_id, record.job_title, record.company,
                )

    # Generate resume tweaks if missing and we have a resume
    if not resume_tweaks and has_resume:
        tweaks_result = pipeline.optimize_resume(job, resume_text)
        if tweaks_result:
            resume_tweaks = tweaks_result
            record.resume_tweaks_json = json.dumps(tweaks_result)
            logger.info(
                "Generated resume tweaks for app %d (%s @ %s)",
                app_id, record.job_title, record.company,
            )

    # Persist any generated materials
    record.updated_at = _utcnow()
    db.commit()
    db.refresh(record)

    applicant_info = config.get("applicant_info", {})

    return {
        "ats_type": ats_type,
        "ats_detected": ats_type is not None,
        "cover_letter": cover_letter,
        "resume_tweaks": resume_tweaks,
        "applicant_info": {
            "first_name": applicant_info.get("first_name", ""),
            "last_name": applicant_info.get("last_name", ""),
            "email": applicant_info.get("email", ""),
            "phone": applicant_info.get("phone", ""),
        },
        "job_title": record.job_title,
        "company": record.company,
        "job_url": job_url,
    }


def submit_application(
    db: Session,
    app_id: int,
    cover_letter: str | None = None,
    dry_run: bool = True,
    profile: str = "default",
    workspace_id: str | None = None,
) -> dict | None:
    """Submit an application to the detected ATS.

    If *cover_letter* is provided (user-edited version), it is saved to
    the DB before submission.  When *dry_run* is ``True``, the ATS call
    is simulated and no real submission occurs.

    Returns a dict matching ``SubmitResponse``, or *None* when the
    application record cannot be found.
    """
    from job_finder.tools.auto_apply_tool import auto_apply, detect_ats_type
    from job_finder.tools.resume_parser_tool import find_resume

    record = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id).first()
    if not record:
        return None

    config = get_config(profile)
    job_url = record.job_url or ""

    # ATS detection
    ats_type = detect_ats_type(job_url) if job_url else None

    # If caller provided an edited cover letter, persist it
    if cover_letter is not None:
        record.cover_letter = cover_letter
        record.updated_at = _utcnow()
        db.commit()
        db.refresh(record)

    # Resolve the cover letter to send (user-edited takes precedence)
    cl_text = cover_letter if cover_letter is not None else (record.cover_letter or "")

    # Locate the resume PDF for attachment — workspace-aware
    resume_path = ""
    if workspace_id:
        from app.services import workspace_service
        resume_record = workspace_service.get_workspace_resume(db, workspace_id)
        if resume_record and resume_record.file_path:
            resume_path = resume_record.file_path
    if not resume_path:
        resume_path = config.get("profile", {}).get("resume_path", "")
    if not resume_path:
        resume_path = find_resume(profile=profile) or ""

    # Build the job dict expected by auto_apply
    job = {
        "title": record.job_title,
        "company": record.company,
        "url": job_url,
    }

    result = auto_apply(
        job=job,
        config=config,
        resume_path=resume_path,
        cover_letter_text=cl_text,
        dry_run=dry_run,
    )

    method = result.get("method")
    success = result.get("success", False)

    # On live successful submission, update status
    if success and not dry_run:
        record.status = "applied"
        record.date_applied = _utcnow()
        record.application_method = method or ""
        record.updated_at = _utcnow()
        db.commit()
        db.refresh(record)
        logger.info(
            "Application %d submitted via %s (%s @ %s)",
            app_id, method, record.job_title, record.company,
        )

    return {
        "success": success,
        "method": method,
        "message": result.get("message", ""),
        "dry_run": dry_run,
    }
