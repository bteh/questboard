"""Resume management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse

from app.schemas.resume import ResumeStatus, ResumeUploadResponse
from app.services import resume_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])


def _analyze_and_update_profile(profile: str) -> None:
    """Background task: analyze resume with LLM and auto-configure profile."""
    try:
        from app.services.resume_analyzer import analyze_resume, apply_analysis_to_profile
        from app.services.settings_service import update_profile_preferences
        from app.dependencies import get_llm, get_config

        resume_text = resume_service.get_resume_text(profile)
        if resume_text.startswith("ERROR"):
            return

        llm = get_llm()
        analysis = analyze_resume(resume_text, llm)
        if not analysis:
            return

        # Load current config and merge analysis
        config = get_config(profile)
        updated = apply_analysis_to_profile(config, analysis)

        # Write updated profile back — only the auto-populated fields
        import yaml
        import os

        config_dir = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
            "src", "job_finder", "config", "profiles",
        )
        profile_path = os.path.join(config_dir, f"{profile}.yaml")

        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        else:
            existing = {}

        # Always overwrite auto-populated fields with fresh analysis.
        # These fields are machine-generated from the resume, so a new resume
        # should always produce fresh values. User-editable fields (like
        # weights, thresholds, locations) are NOT touched here.
        for key in ("target_roles", "keyword_searches", "keywords", "career_baseline", "_resume_analysis"):
            if key not in updated:
                continue
            updated_val = updated.get(key)
            if key == "keywords":
                existing["keywords"] = updated_val or {}
            elif key == "career_baseline":
                existing["career_baseline"] = updated_val or {}
            else:
                existing[key] = updated_val

        with open(profile_path, "w", encoding="utf-8") as f:
            yaml.dump(existing, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        logger.info("Auto-configured profile '%s' from resume analysis", profile)

    except Exception as e:
        logger.warning("Resume analysis background task failed (non-fatal): %s", e)


@router.get("/{profile}", response_model=ResumeStatus)
async def get_resume_status(profile: str):
    """Check if a resume exists for the given profile."""
    return resume_service.get_resume_status(profile)


@router.post("/{profile}/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    profile: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload a resume PDF for the given profile.

    After saving the file, kicks off a background LLM analysis that
    auto-extracts skills, seniority, and industry from the resume and
    populates the profile's target roles, keywords, and career baseline.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    result = resume_service.upload_resume(profile, file.filename, content)

    # Trigger async resume analysis in the background
    background_tasks.add_task(_analyze_and_update_profile, profile)

    return result


@router.get("/{profile}/download")
async def download_resume(profile: str):
    """Download the resume PDF for the given profile."""
    path = resume_service.get_resume_path(profile)
    if not path:
        raise HTTPException(404, f"No resume found for profile '{profile}'")
    return FileResponse(path, media_type="application/pdf", filename=f"{profile}_resume.pdf")


@router.get("/{profile}/text")
async def get_resume_text(profile: str):
    """Get parsed text content of the resume."""
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
    resume_text = resume_service.get_resume_text(profile)
    if resume_text.startswith("ERROR"):
        raise HTTPException(404, resume_text)

    from app.services.resume_analyzer import analyze_resume, apply_analysis_to_profile
    from app.dependencies import get_llm

    llm = get_llm()
    analysis = analyze_resume(resume_text, llm)
    if not analysis:
        raise HTTPException(
            503,
            "LLM not available — configure an LLM provider in Settings to enable resume analysis",
        )

    return {
        "profile": profile,
        "analysis": analysis,
        "message": "Resume analyzed successfully. Profile keywords and roles will be updated.",
    }
