"""Resume management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from app.schemas.resume import ResumeStatus, ResumeUploadResponse
from app.services import resume_service
from app.dependencies import reject_legacy_route_in_hosted_mode, sanitize_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])


def _analyze_and_update_profile(profile: str) -> None:
    """Analyze a resume and persist updated profile fields."""
    try:
        from app.services.resume_analyzer import analyze_resume, persist_analysis_to_profile
        from app.dependencies import get_llm, get_config

        resume_text = resume_service.get_resume_text(profile)
        if resume_text.startswith("ERROR"):
            return

        llm = get_llm()
        analysis = analyze_resume(resume_text, llm)
        if not analysis:
            return

        config = get_config(profile)
        persist_analysis_to_profile(
            profile,
            analysis,
            profile_config=config,
            force_overwrite=True,
        )

    except Exception as e:
        logger.warning("Resume analysis update failed (non-fatal): %s", e)


@router.get("/{profile}", response_model=ResumeStatus)
async def get_resume_status(profile: str):
    """Check if a resume exists for the given profile."""
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    return resume_service.get_resume_status(profile)


@router.post("/{profile}/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    profile: str,
    file: UploadFile = File(...),
):
    """Upload a resume PDF for the given profile.

    After saving the file, analyzes the resume when an LLM is configured and
    auto-extracts skills, seniority, and industry from the resume and
    populates the profile's target roles, keywords, and career baseline.
    """
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10MB)")
    if not content:
        raise HTTPException(400, "Empty file")

    result = resume_service.upload_resume(profile, file.filename, content)
    _analyze_and_update_profile(profile)

    return result


@router.get("/{profile}/download")
async def download_resume(profile: str):
    """Download the resume PDF for the given profile."""
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    path = resume_service.get_resume_path(profile)
    if not path:
        raise HTTPException(404, f"No resume found for profile '{profile}'")
    return FileResponse(path, media_type="application/pdf", filename=f"{profile}_resume.pdf")


@router.get("/{profile}/text")
async def get_resume_text(profile: str):
    """Get parsed text content of the resume."""
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    text = resume_service.get_resume_text(profile)
    if text.startswith("ERROR"):
        raise HTTPException(404, text)
    return {"profile": profile, "text": text}


@router.post("/{profile}/analyze")
async def analyze_resume_endpoint(profile: str):
    """Manually trigger resume analysis and profile auto-configuration.

    Useful for re-analyzing after the user updates their resume or
    when they want to refresh the extracted data.
    """
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    resume_text = resume_service.get_resume_text(profile)
    if resume_text.startswith("ERROR"):
        raise HTTPException(404, resume_text)

    from app.services.resume_analyzer import analyze_resume, persist_analysis_to_profile
    from app.dependencies import get_llm, get_config

    llm = get_llm()
    analysis = analyze_resume(resume_text, llm)
    if not analysis:
        raise HTTPException(
            503,
            "LLM not available — configure an LLM provider in Settings to enable resume analysis",
        )

    updated = persist_analysis_to_profile(
        profile,
        analysis,
        profile_config=get_config(profile),
        force_overwrite=True,
    )

    return {
        "profile": profile,
        "analysis": analysis,
        "updated_profile": updated,
        "message": "Resume analyzed successfully and profile fields were updated.",
    }
