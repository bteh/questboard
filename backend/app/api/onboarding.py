"""Hosted onboarding endpoints for anonymous workspaces."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import get_workspace_context, get_workspace_context_csrf
from app.models.database import get_db
from app.schemas.workspace import (
    GeneratedProfileResponse,
    OnboardingState,
    WorkspacePreferences,
    WorkspaceResumeUploadResponse,
    WorkspaceSearchRunResponse,
)
from app.security import enforce_rate_limit, request_identity
from app.services import pipeline_service, workspace_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# In-memory cache for generated profiles, keyed on (workspace_id, resume_hash).
# The LLM call is expensive enough that we don't want to re-run it on every
# tab refresh — but a real user updating their resume MUST get a fresh
# profile, hence keying on the content hash. 24-hour TTL is a soft cap.
_GENERATED_PROFILE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_GENERATED_PROFILE_TTL_SECONDS = 24 * 60 * 60


def _cache_get(workspace_id: str, resume_hash: str) -> dict | None:
    entry = _GENERATED_PROFILE_CACHE.get((workspace_id, resume_hash))
    if not entry:
        return None
    ts, payload = entry
    if time.time() - ts > _GENERATED_PROFILE_TTL_SECONDS:
        _GENERATED_PROFILE_CACHE.pop((workspace_id, resume_hash), None)
        return None
    return payload


def _cache_put(workspace_id: str, resume_hash: str, payload: dict) -> None:
    _GENERATED_PROFILE_CACHE[(workspace_id, resume_hash)] = (time.time(), payload)


@router.get("/state", response_model=OnboardingState)
def get_state(
    context = Depends(get_workspace_context),
    db: Session = Depends(get_db),
):
    return workspace_service.get_onboarding_state(db, context.workspace.id)


@router.post("/resume", response_model=WorkspaceResumeUploadResponse)
async def upload_workspace_resume(
    request: Request,
    file: UploadFile = File(...),
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    enforce_rate_limit(
        "resume-upload",
        request_identity(request, context.workspace.id),
        limit=settings.upload_rate_limit_per_minute,
        db=db,
    )
    # Read with a size cap to prevent OOM from accidental large uploads.
    # 10MB matches the limit enforced in save_workspace_resume, but we
    # reject early before buffering the entire file into memory.
    max_bytes = 10 * 1024 * 1024  # 10 MB
    content = await file.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")
    resume, analysis = workspace_service.save_workspace_resume(
        db,
        context.workspace.id,
        file.filename or "resume.pdf",
        content,
    )
    return WorkspaceResumeUploadResponse(resume=resume, analysis=analysis)


@router.post("/preferences", response_model=WorkspacePreferences)
def save_preferences(
    request: Request,
    body: WorkspacePreferences,
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    enforce_rate_limit(
        "workspace-prefs",
        request_identity(request, context.workspace.id),
        limit=settings.search_rate_limit_per_minute,
        db=db,
    )
    return workspace_service.save_workspace_preferences(db, context.workspace.id, body)


@router.post("/search", response_model=WorkspaceSearchRunResponse)
async def start_onboarding_search(
    request: Request,
    body: WorkspacePreferences,
    context = Depends(get_workspace_context_csrf),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    enforce_rate_limit(
        "onboarding-search",
        request_identity(request, context.workspace.id),
        limit=settings.search_rate_limit_per_minute,
        db=db,
    )
    prefs = workspace_service.save_workspace_preferences(db, context.workspace.id, body)
    labels = workspace_service.place_labels(prefs.preferred_places)
    effective_workplace_preference = workspace_service.effective_workplace_preference(
        prefs.workplace_preference,
        prefs.preferred_places,
    )
    if not workspace_service.workspace_locations_are_runnable(prefs):
        raise HTTPException(
            status_code=400,
            detail="Add at least one preferred location, or switch to Remote + selected places / Remote only.",
        )

    # When no roles/keywords, try to derive from the uploaded resume
    if not prefs.roles and not prefs.keywords:
        resume_record = workspace_service.get_workspace_resume(db, context.workspace.id)
        if resume_record and resume_record.extracted_text:
            fallback_roles, fallback_keywords = workspace_service.derive_search_terms_from_resume(
                db, context.workspace.id, prefs,
            )
            if fallback_roles or fallback_keywords:
                prefs = prefs.model_copy(update={
                    "roles": fallback_roles,
                    "keywords": fallback_keywords,
                })
        if not prefs.roles and not prefs.keywords:
            raise HTTPException(status_code=400, detail="Add at least one role or keyword, or upload a resume")

    snapshot = workspace_service.build_search_snapshot(prefs)
    llm = workspace_service.get_workspace_llm(db, context.workspace.id, fallback_to_global=True)

    run = pipeline_service.start_run(
        roles=prefs.roles or prefs.keywords,
        locations=labels,
        keywords=prefs.keywords,
        companies=prefs.companies,
        include_remote=effective_workplace_preference != "location_only",
        workplace_preference=effective_workplace_preference,
        max_days_old=prefs.max_days_old,
        use_ai=bool(llm and llm.is_configured),
        profile="workspace",
        mode="search_score",
        loop=asyncio.get_running_loop(),
        workspace_id=context.workspace.id,
        config_override=workspace_service.build_pipeline_config_override(prefs, context.workspace.id),
        llm_override=llm,
        snapshot=snapshot,
    )
    return WorkspaceSearchRunResponse(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.post("/generate-profile", response_model=GeneratedProfileResponse)
def generate_workspace_profile(
    request: Request,
    context = Depends(get_workspace_context),
    db: Session = Depends(get_db),
):
    """Generate an LLM-tailored search profile from the workspace's resume.

    The whole point: instead of forcing the user to pick from the seven
    hardcoded archetype templates, the LLM reads their resume and
    produces a profile *specifically for them* — covering niches we
    never modeled (climate tech, vet med, MTS at frontier labs,
    biotech regulatory, founding engineers at web3 startups, etc.).

    Returns 400 if no resume has been uploaded yet, 503 if the LLM is
    not configured or returned an unusable result. The frontend handles
    both as "fall back to template picker".

    Cached per (workspace_id, resume_content_hash) so opening the
    dashboard repeatedly doesn't burn LLM credits — and changing the
    resume invalidates automatically.
    """
    settings = get_settings()
    enforce_rate_limit(
        "generate-profile",
        request_identity(request, context.workspace.id),
        limit=settings.search_rate_limit_per_minute,
        db=db,
    )

    resume_text = workspace_service.get_resume_text(db, context.workspace.id)
    if not resume_text or not resume_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Upload a resume first — profile generation needs your resume text to work.",
        )

    # Hash the resume text so we cache by content, not by upload event.
    # If the user re-uploads the same file, no LLM call. If they edit and
    # re-upload, we generate a fresh profile.
    resume_hash = hashlib.sha256(resume_text.encode("utf-8", errors="ignore")).hexdigest()[:16]
    cached = _cache_get(context.workspace.id, resume_hash)
    if cached:
        logger.info("generate_profile: cache hit for workspace=%s", context.workspace.id)
        return GeneratedProfileResponse(**{**cached, "cached": True})

    llm = workspace_service.get_workspace_llm(db, context.workspace.id, fallback_to_global=True)
    if not llm or not llm.is_configured:
        raise HTTPException(
            status_code=503,
            detail="No AI provider connected. Connect one in Settings or pick a template manually.",
        )

    # Build a pipeline instance with all attributes properly initialized.
    # Override config after construction so workspace preferences take
    # effect, but self.profile_name and self._preloaded_resume_text are
    # set correctly (the old __new__ approach left them uninitialized).
    from job_finder.pipeline import JobFinderPipeline

    pipeline = JobFinderPipeline(llm=llm, profile="workspace")
    pipeline.config = workspace_service.build_pipeline_config_override(
        workspace_service.get_workspace_preferences(db, context.workspace.id),
        context.workspace.id,
    )

    profile = pipeline.generate_profile_from_resume(resume_text)
    if profile is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI couldn't generate a profile from your resume. This usually "
                "means the LLM call failed or the response didn't match the schema. "
                "Try a template instead, or check your AI provider in Settings."
            ),
        )

    _cache_put(context.workspace.id, resume_hash, profile)
    logger.info(
        "generate_profile: cache miss, generated for workspace=%s archetype=%r confidence=%.2f",
        context.workspace.id,
        profile.get("detected_archetype"),
        profile.get("confidence", 0.0),
    )
    return GeneratedProfileResponse(**{**profile, "cached": False})
