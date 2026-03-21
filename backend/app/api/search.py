"""Search & pipeline execution endpoints with SSE progress streaming."""

from __future__ import annotations

import asyncio
import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import logging
from sqlalchemy.orm import Session

from app.schemas.search import RunResult, RunStatus, SearchDefaults, SearchRequest, SearchSuggestions
from app.services import pipeline_service, resume_service, workspace_service
from app.dependencies import get_config, get_llm, sanitize_profile
from app.models.database import get_db
from app.security import enforce_rate_limit, request_identity
from app.config import get_settings
from app.schemas.workspace import PlaceSelection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def _clean_search_terms(values: list[str] | None) -> list[str]:
    """Return only non-empty search terms."""
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str) and value.strip()]


def _clean_locations(values: list[str] | None) -> list[str]:
    """Return only non-remote location strings."""
    merged_values: list[str] = []
    raw_values = [value for value in values or [] if isinstance(value, str) and value.strip()]
    i = 0
    while i < len(raw_values):
        current = raw_values[i].strip()
        nxt = raw_values[i + 1].strip() if i + 1 < len(raw_values) else ""
        if (
            current
            and nxt
            and "," not in current
            and len(nxt) == 2
            and nxt.isalpha()
        ):
            merged_values.append(f"{current}, {nxt.upper()}")
            i += 2
            continue
        merged_values.append(current)
        i += 1

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in merged_values:
        item = value.strip()
        if not item:
            continue
        if item.lower() in {"remote", "anywhere", "united states", "usa", "us"}:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(item)
    return cleaned


def _derive_workplace_preference(cfg: dict) -> str:
    """Infer the active workplace preference from config."""
    loc_prefs = cfg.get("location_preferences", {})
    stored = loc_prefs.get("workplace_preference")
    if stored in {"remote_friendly", "remote_only", "location_only"}:
        return stored
    if loc_prefs.get("remote_only", False):
        return "remote_only"
    if "include_remote" in loc_prefs:
        return "remote_friendly" if loc_prefs.get("include_remote", True) else "location_only"

    locations = [value.lower() for value in _clean_search_terms(cfg.get("locations"))]
    return "remote_friendly" if "remote" in locations else "location_only"


def _authorize_run_access(run, workspace) -> None:
    if get_settings().hosted_mode and not workspace:
        raise HTTPException(404, "Run not found")
    if run.workspace_id and (not workspace or workspace.workspace.id != run.workspace_id):
        raise HTTPException(404, "Run not found")


@router.post("/run", response_model=RunStatus)
async def start_search_run(
    req: SearchRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Start a pipeline run. Returns immediately with a run_id for progress tracking."""
    logger.info("Search request: %d roles, %d keywords, %d companies", len(req.roles), len(req.keywords), len(req.companies))
    if not req.roles and not req.keywords:
        raise HTTPException(400, "At least one role or keyword is required")
    if req.workplace_preference != "remote_only" and not req.locations:
        raise HTTPException(400, "At least one location is required")

    workspace = workspace_service.get_workspace_context_optional(db, request)
    if workspace:
        enforce_rate_limit(
            "search-run",
            request_identity(request, workspace.workspace.id),
            limit=get_settings().search_rate_limit_per_minute,
        )

    loop = asyncio.get_running_loop()
    config_override = None
    llm_override = None
    if workspace:
        prefs = workspace_service.get_workspace_preferences(db, workspace.workspace.id)
        merged_prefs = prefs.model_copy(
            update={
                "roles": req.roles,
                "keywords": req.keywords,
                "preferred_places": [PlaceSelection(label=location) for location in req.locations],
                "workplace_preference": req.workplace_preference,
                "max_days_old": req.max_days_old,
            }
        )
        config_override = workspace_service.build_pipeline_config_override(
            merged_prefs,
            workspace.workspace.id,
        )
        llm_override = workspace_service.get_workspace_llm(
            db,
            workspace.workspace.id,
            fallback_to_global=True,
        )

    run = pipeline_service.start_run(
        roles=req.roles,
        locations=req.locations,
        keywords=req.keywords,
        companies=req.companies,
        include_remote=req.include_remote,
        workplace_preference=req.workplace_preference,
        max_days_old=req.max_days_old,
        use_ai=req.use_ai,
        profile="workspace" if workspace else req.profile,
        mode=req.mode,
        loop=loop,
        workspace_id=workspace.workspace.id if workspace else None,
        config_override=config_override,
        llm_override=llm_override,
    )
    if workspace and config_override:
        snapshot = workspace_service.build_search_snapshot(
            workspace_service.get_workspace_preferences(db, workspace.workspace.id).model_copy(
                update={
                    "roles": req.roles,
                    "keywords": req.keywords,
                    "preferred_places": [PlaceSelection(label=location) for location in req.locations],
                    "workplace_preference": req.workplace_preference,
                    "max_days_old": req.max_days_old,
                }
            )
        )
        workspace_service.register_search_run(
            db,
            workspace.workspace.id,
            run.run_id,
            run.status,
            run.mode,
            snapshot,
            run.started_at,
        )
    return RunStatus(
        run_id=run.run_id,
        status=run.status,
        started_at=run.started_at,
    )


@router.get("/runs/{run_id}/progress")
async def stream_run_progress(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """SSE stream of pipeline progress messages."""
    run = pipeline_service.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    workspace = workspace_service.get_workspace_context_optional(db, request)
    _authorize_run_access(run, workspace)
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
async def get_run_status(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Poll-based fallback for run status."""
    run = pipeline_service.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    workspace = workspace_service.get_workspace_context_optional(db, request)
    _authorize_run_access(run, workspace)
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
async def list_runs(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """List recent pipeline runs."""
    workspace = workspace_service.get_workspace_context_optional(db, request)
    if get_settings().hosted_mode and not workspace:
        return []
    runs = pipeline_service.list_runs(
        limit=limit,
        workspace_id=workspace.workspace.id if workspace else None,
    )
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
async def get_search_defaults(
    request: Request,
    profile: str = "default",
    db: Session = Depends(get_db),
):
    """Return default search parameters from the active profile."""
    workspace = workspace_service.get_workspace_context_optional(db, request)
    if workspace:
        prefs = workspace_service.get_workspace_preferences(db, workspace.workspace.id)
        return SearchDefaults(
            roles=prefs.roles,
            locations=workspace_service.place_labels(prefs.preferred_places),
            keywords=prefs.keywords,
            include_remote=prefs.workplace_preference != "location_only",
            workplace_preference=prefs.workplace_preference,
            max_days_old=prefs.max_days_old,
            profile="workspace",
            current_title=prefs.current_title,
            current_level=prefs.current_level,
            current_tc=prefs.compensation.current_comp,
            min_base=prefs.compensation.min_base,
            target_total_comp=prefs.compensation.target_total_comp,
            min_acceptable_tc=prefs.compensation.min_acceptable_tc,
            compensation_currency=prefs.compensation.currency,
            compensation_period=prefs.compensation.pay_period,
            exclude_staffing_agencies=prefs.exclude_staffing_agencies,
        )

    profile = sanitize_profile(profile)
    cfg = get_config(profile if profile != "default" else None)
    workplace_preference = _derive_workplace_preference(cfg)
    return SearchDefaults(
        roles=_clean_search_terms(cfg.get("target_roles")),
        locations=_clean_locations(cfg.get("location_preferences", {}).get("preferred_locations") or cfg.get("locations")),
        keywords=_clean_search_terms(cfg.get("keyword_searches")),
        include_remote=workplace_preference != "location_only",
        workplace_preference=workplace_preference,
        max_days_old=cfg.get("search_settings", {}).get("max_days_old", 14),
        profile=profile,
        current_title=cfg.get("career_baseline", {}).get("current_title", ""),
        current_level=cfg.get("career_baseline", {}).get("current_level", ""),
        current_tc=cfg.get("career_baseline", {}).get("current_tc"),
        min_base=cfg.get("compensation", {}).get("min_base"),
        target_total_comp=cfg.get("compensation", {}).get("target_total_comp"),
        min_acceptable_tc=cfg.get("career_baseline", {}).get("min_acceptable_tc"),
        compensation_currency=cfg.get("compensation", {}).get("currency", "USD"),
        compensation_period=cfg.get("compensation", {}).get("pay_period", "annual"),
        exclude_staffing_agencies=cfg.get("search_settings", {}).get("exclude_staffing_agencies", True),
    )


_SUGGEST_PROMPT = """Analyze the resume and return valid JSON with these keys:

- "roles": 8-12 job titles to search for, matching the resume's seniority level. Include title variations.
- "keywords": 8-15 domain-specific terms from their experience that appear in relevant job postings. No generic words.
- "locations": 1-3 locations from the resume plus "Remote".
- "summary": one-sentence candidate profile summary.
- "companies": 30-60 companies this person should target. Mix large employers, growth-stage, and smaller/emerging organizations. Examples by field:
  Tech: Stripe, Databricks, RunwayML. Healthcare: Kaiser, One Medical, Cityblock. Finance: JPMorgan, Brex, Ramp. Media: Netflix, A24, Spotify. Education: Khan Academy, Coursera. Adapt to the resume's actual field.

Works for any profession. Be specific and practical — these are used as literal search queries."""

# In-memory cache keyed by resume hash — avoids re-analyzing the same resume.
_suggest_cache: dict[str, SearchSuggestions] = {}
_CACHE_MAX = 20


def _clean_list(raw: list | None, max_items: int = 20, max_len: int = 100) -> list[str]:
    """Sanitize LLM output — enforce string lists and reasonable lengths."""
    if not isinstance(raw, list):
        return []
    return [str(item)[:max_len] for item in raw if isinstance(item, (str, int, float))][:max_items]


def _get_fast_llm(primary_llm) -> tuple:
    """Return a fast LLM for the suggest endpoint.

    If the user's configured provider is already fast (Groq, Cerebras,
    Gemini, Ollama), use it directly. Otherwise, try known fast free
    providers. Returns (llm, model_override | None).
    """
    from job_finder.llm_client import LLMClient, PRESETS

    fast_providers = {"groq", "cerebras", "gemini", "ollama"}

    # User's provider is already fast
    if primary_llm and primary_llm.provider in fast_providers:
        return primary_llm, None

    # Try fast free providers that don't need an API key from the user
    for provider in ["groq", "cerebras", "gemini"]:
        preset = PRESETS.get(provider, {})
        api_key = os.getenv(f"{provider.upper()}_API_KEY", "") or preset.get("api_key", "")
        if api_key:
            try:
                fast = LLMClient(provider=provider, api_key=api_key)
                if fast.is_configured:
                    logger.info("Using fast provider '%s' for suggest", provider)
                    return fast, None
            except Exception:
                continue

    # Fall back to the user's configured LLM
    return primary_llm, None


@router.post("/suggest", response_model=SearchSuggestions)
async def suggest_search_params(
    request: Request,
    profile: str = "default",
    db: Session = Depends(get_db),
):
    """Use LLM to analyze resume and suggest search parameters.

    Single LLM call with aggressive truncation. Tries fast providers
    (Groq/Cerebras/Gemini) before falling back to the user's model.
    Results are cached per resume hash to avoid redundant calls.
    """
    workspace = workspace_service.get_workspace_context_optional(db, request)
    settings = get_settings()
    enforce_rate_limit(
        "search-suggest",
        request_identity(request, workspace.workspace.id if workspace else None),
        limit=settings.search_rate_limit_per_minute,
    )
    primary_llm = (
        workspace_service.get_workspace_llm(db, workspace.workspace.id, fallback_to_global=True)
        if workspace
        else get_llm()
    )
    if not primary_llm or not primary_llm.is_configured:
        raise HTTPException(400, "No LLM provider configured. Connect one in Settings first.")

    if workspace:
        resume_text = workspace_service.get_resume_text(db, workspace.workspace.id)
    else:
        profile = sanitize_profile(profile)
        resume_text = resume_service.get_resume_text(profile)
    if not resume_text or resume_text.startswith("ERROR"):
        raise HTTPException(400, "No resume found. Upload one in Settings first.")

    # Aggressive truncation — extraction only needs key sections
    if len(resume_text) > 4000:
        resume_text = resume_text[:4000] + "\n...(truncated)"

    # Check cache
    cache_key = hashlib.sha256(resume_text.encode()).hexdigest()[:16]
    if cache_key in _suggest_cache:
        logger.info("Suggest cache hit for %s", cache_key)
        return _suggest_cache[cache_key]

    # Use a fast provider if available, otherwise fall back to user's model
    llm, _model = _get_fast_llm(primary_llm)
    user_msg = f"Resume:\n\n{resume_text}"

    data = await asyncio.to_thread(
        llm.chat_json, _SUGGEST_PROMPT, user_msg, max_tokens=2048,
    )

    if not data:
        # Retry with the primary LLM if the fast provider failed
        if llm is not primary_llm:
            logger.warning("Fast provider failed, retrying with primary LLM")
            data = await asyncio.to_thread(
                primary_llm.chat_json, _SUGGEST_PROMPT, user_msg, max_tokens=2048,
            )
        if not data:
            raise HTTPException(502, "LLM failed to generate suggestions. Try again.")

    result = SearchSuggestions(
        roles=_clean_list(data.get("roles"), max_items=15),
        keywords=_clean_list(data.get("keywords"), max_items=20),
        locations=_clean_list(data.get("locations"), max_items=5),
        companies=_clean_list(data.get("companies"), max_items=100),
        summary=str(data.get("summary", ""))[:300],
    )

    # Cache result (evict oldest if full)
    if len(_suggest_cache) >= _CACHE_MAX:
        _suggest_cache.pop(next(iter(_suggest_cache)))
    _suggest_cache[cache_key] = result

    return result
