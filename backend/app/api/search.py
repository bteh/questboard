"""Search & pipeline execution endpoints with SSE progress streaming."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import logging

from app.schemas.search import RunResult, RunStatus, SearchDefaults, SearchRequest, SearchSuggestions
from app.services import pipeline_service, resume_service
from app.dependencies import get_config, get_llm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/run", response_model=RunStatus)
async def start_search_run(req: SearchRequest):
    """Start a pipeline run. Returns immediately with a run_id for progress tracking."""
    if not req.roles and not req.keywords:
        raise HTTPException(400, "At least one role or keyword is required")
    if not req.locations:
        raise HTTPException(400, "At least one location is required")

    loop = asyncio.get_running_loop()
    run = pipeline_service.start_run(
        roles=req.roles,
        locations=req.locations,
        keywords=req.keywords,
        include_remote=req.include_remote,
        max_days_old=req.max_days_old,
        use_ai=req.use_ai,
        profile=req.profile,
        mode=req.mode,
        loop=loop,
    )
    return RunStatus(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
    )


@router.get("/runs/{run_id}/progress")
async def stream_run_progress(run_id: str):
    """SSE stream of pipeline progress messages."""
    run = pipeline_service.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return StreamingResponse(
        pipeline_service.stream_progress(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs/{run_id}/status", response_model=RunStatus)
async def get_run_status(run_id: str):
    """Poll-based fallback for run status."""
    run = pipeline_service.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return RunStatus(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        progress_messages=run.progress_messages,
        jobs_found=run.jobs_found,
        jobs_scored=run.jobs_scored,
        error=run.error,
    )


@router.get("/runs", response_model=list[RunStatus])
async def list_runs(limit: int = 20):
    """List recent pipeline runs."""
    runs = pipeline_service.list_runs(limit=limit)
    return [
        RunStatus(
            run_id=r.run_id,
            status=r.status,
            started_at=r.started_at,
            completed_at=r.completed_at,
            progress_messages=r.progress_messages,
            jobs_found=r.jobs_found,
            jobs_scored=r.jobs_scored,
            error=r.error,
        )
        for r in runs
    ]


@router.get("/defaults", response_model=SearchDefaults)
async def get_search_defaults(profile: str = "default"):
    """Return default search parameters from the active profile."""
    cfg = get_config(profile if profile != "default" else None)
    return SearchDefaults(
        roles=cfg.get("target_roles", []),
        locations=cfg.get("locations", []),
        keywords=cfg.get("keyword_searches", []),
        max_days_old=cfg.get("search_settings", {}).get("max_days_old", 14),
        profile=profile,
    )


_SUGGEST_PROMPT = """You are a career strategist. Analyze the resume below and suggest job search parameters.

Return valid JSON with exactly these keys:
- "roles": list of 8-12 job titles this person should search for, ordered from most to least relevant. Include variations (e.g. "Senior Software Engineer", "Staff Engineer", "Engineering Manager"). Match the seniority level evident in the resume.
- "keywords": list of 8-15 high-signal technical keywords and domain terms from their experience that would appear in relevant job descriptions. Focus on specific technologies, frameworks, and domain terms — not generic words like "engineering" or "software".
- "locations": list of 1-3 locations. If the resume mentions a city, include it. Always include "Remote" as an option.
- "summary": a one-sentence summary of the candidate's profile (e.g. "Senior data engineer with 8 years of experience building data platforms at scale").

Be specific and practical. These will be used as literal search queries on job boards."""


@router.post("/suggest", response_model=SearchSuggestions)
async def suggest_search_params(profile: str = "default"):
    """Use LLM to analyze resume and suggest search parameters."""
    llm = get_llm()
    if not llm.is_configured:
        raise HTTPException(400, "No LLM provider configured. Connect one in Settings first.")

    resume_text = resume_service.get_resume_text(profile)
    if not resume_text or resume_text.startswith("ERROR"):
        raise HTTPException(400, "No resume found. Upload one in Settings first.")

    # Truncate very long resumes to avoid token limits
    if len(resume_text) > 8000:
        resume_text = resume_text[:8000] + "\n...(truncated)"

    result = llm.chat_json(_SUGGEST_PROMPT, f"Resume:\n\n{resume_text}")
    if not result:
        raise HTTPException(502, "LLM failed to generate suggestions. Try again.")

    return SearchSuggestions(
        roles=result.get("roles", []),
        keywords=result.get("keywords", []),
        locations=result.get("locations", []),
        summary=result.get("summary", ""),
    )
