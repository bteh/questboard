"""Hosted onboarding endpoints for anonymous workspaces."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dependencies import get_workspace_context, get_workspace_context_csrf
from app.models.database import get_db
from app.schemas.workspace import (
    OnboardingState,
    WorkspacePreferences,
    WorkspaceResumeUploadResponse,
    WorkspaceSearchRunResponse,
)
from app.security import enforce_rate_limit, request_identity
from app.services import pipeline_service, workspace_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


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
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
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
