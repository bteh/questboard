"""Resume management endpoints."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from app.schemas.resume import ResumeStatus, ResumeUploadResponse
from app.services import resume_service
from app.dependencies import reject_legacy_route_in_hosted_mode, sanitize_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])

_ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")
_SCANNED_PDF_MIN_CHARS = 200
_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def _save_resume_file(profile: str, filename: str, content: bytes) -> dict:
    """Save an uploaded resume, preserving the original extension.

    Mirrors ``resume_service.upload_resume`` (which is PDF-only) but writes
    ``{profile}_resume{ext}`` and removes stale copies with other extensions
    so ``find_resume()`` always picks up the latest upload.
    """
    ext = os.path.splitext(filename)[1].lower()
    target_name = f"{profile}_resume{ext}"

    knowledge_dirs = [resume_service._KNOWLEDGE_DIR]
    cwd_knowledge = os.path.join(os.getcwd(), "knowledge")
    if os.path.realpath(cwd_knowledge) != os.path.realpath(resume_service._KNOWLEDGE_DIR):
        knowledge_dirs.append(cwd_knowledge)

    for directory in knowledge_dirs:
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, target_name), "wb") as f:
            f.write(content)
        for other_ext in _ALLOWED_EXTENSIONS:
            if other_ext == ext:
                continue
            stale = os.path.join(directory, f"{profile}_resume{other_ext}")
            if os.path.exists(stale):
                try:
                    os.remove(stale)
                except OSError:
                    pass

    # Store the user's original filename for display
    with open(resume_service._original_name_path(profile), "w", encoding="utf-8") as f:
        f.write(filename)

    return {
        "profile": profile,
        "filename": filename,
        "message": "Resume uploaded successfully",
    }


def _build_analysis_summary(analysis: dict) -> dict:
    """Shape the raw LLM analysis into the upload-response summary contract."""

    def _str_list(key: str) -> list[str]:
        values = analysis.get(key)
        if not isinstance(values, list):
            return []
        return [v for v in values if isinstance(v, str)]

    education: list[dict] = []
    for entry in analysis.get("education") or []:
        if isinstance(entry, dict):
            education.append(
                {
                    "degree": str(entry.get("degree") or "").strip(),
                    "field": str(entry.get("field") or "").strip(),
                    "institution": str(entry.get("institution") or "").strip(),
                }
            )

    return {
        "skills": _str_list("skills"),
        "suggested_target_roles": _str_list("suggested_target_roles"),
        "suggested_keywords": _str_list("suggested_keywords"),
        "current_title": str(analysis.get("current_title") or "").strip(),
        "seniority": str(analysis.get("seniority") or "").strip(),
        "certifications": _str_list("certifications"),
        "education": education,
    }


def _analyze_and_update_profile(profile: str) -> tuple[str, dict | None]:
    """Analyze a resume and persist updated profile fields.

    Returns ``(analysis_status, analysis_summary)`` where status is one of
    ``completed``, ``skipped_no_llm``, or ``failed``.
    """
    try:
        from app.services.resume_analyzer import analyze_resume, persist_analysis_to_profile
        from app.dependencies import get_llm, get_config

        resume_text = resume_service.get_resume_text(profile)
        if resume_text.startswith("ERROR") or resume_text.startswith("WARNING"):
            return "failed", None

        llm = get_llm()
        if not getattr(llm, "is_configured", False):
            logger.info("No LLM configured — resume analysis skipped for '%s'", profile)
            return "skipped_no_llm", None

        analysis = analyze_resume(resume_text, llm)
        if not analysis:
            return "failed", None

        config = get_config(profile)
        persist_analysis_to_profile(
            profile,
            analysis,
            profile_config=config,
            force_overwrite=True,
        )
        return "completed", _build_analysis_summary(analysis)

    except Exception as e:
        logger.warning("Resume analysis update failed (non-fatal): %s", e)
        return "failed", None


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
    """Upload a resume (PDF, DOCX, or TXT) for the given profile.

    After saving the file, analyzes the resume when an LLM is configured and
    auto-extracts skills, seniority, and industry from the resume and
    populates the profile's target roles, keywords, and career baseline.

    The response reports parse status (scanned/image-based PDFs are flagged
    with ``parse_code='SCANNED_PDF'``) and whether analysis ran.
    """
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if not filename or ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Only PDF, DOCX, or TXT files are accepted")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10MB)")
    if not content:
        raise HTTPException(400, "Empty file")

    result = _save_resume_file(profile, filename, content)
    response: dict = {
        **result,
        "parse_status": "ok",
        "parse_code": None,
        "analysis_status": "skipped_no_llm",
        "analysis": None,
    }

    resume_text = resume_service.get_resume_text(profile)
    parse_failed = resume_text.startswith("ERROR") or resume_text.startswith("WARNING")

    if ext == ".pdf" and (parse_failed or len(resume_text.strip()) < _SCANNED_PDF_MIN_CHARS):
        # The file is kept either way — the user may still download it.
        response["parse_status"] = "error"
        response["parse_code"] = "SCANNED_PDF"
        response["analysis_status"] = "failed"
        response["message"] = (
            "Resume saved, but no text could be extracted — the PDF appears to be "
            "scanned/image-based. Upload a text-based PDF, DOCX, or TXT to enable analysis."
        )
        return response

    if parse_failed:
        response["parse_status"] = "error"
        response["analysis_status"] = "failed"
        response["message"] = "Resume saved, but its text could not be parsed."
        return response

    analysis_status, analysis_summary = _analyze_and_update_profile(profile)
    response["analysis_status"] = analysis_status
    response["analysis"] = analysis_summary
    return response


@router.get("/{profile}/download")
async def download_resume(profile: str):
    """Download the resume file for the given profile."""
    reject_legacy_route_in_hosted_mode("Resume profile routes are disabled in hosted mode")
    profile = sanitize_profile(profile)
    path = resume_service.get_resume_path(profile)
    if not path:
        raise HTTPException(404, f"No resume found for profile '{profile}'")
    ext = os.path.splitext(path)[1].lower()
    media_type = _MEDIA_TYPES.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=f"{profile}_resume{ext}")


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
