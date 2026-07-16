"""Pipeline execution service with thread-based concurrency and SSE progress."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.dependencies import get_pipeline

logger = logging.getLogger(__name__)

# Stage weights — how much of total time each stage takes (approximately)
_STAGE_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    "search_only": [("searching", 0.90), ("saving", 0.10)],
    "search_score": [("searching", 0.35), ("scoring", 0.35), ("ai_scoring", 0.20), ("saving", 0.10)],
    "full_pipeline": [("searching", 0.20), ("scoring", 0.20), ("ai_scoring", 0.15), ("enhancing", 0.35), ("saving", 0.10)],
}

_MODE_LABELS: dict[str, str] = {
    "search_only": "Search",
    "search_score": "Search & Score",
    "full_pipeline": "Full AI Agent",
}

_STAGE_LABELS: dict[str, str] = {
    "queued": "Queued for worker",
    "searching": "Searching job boards",
    "scoring": "Scoring jobs",
    "ai_scoring": "AI analysis",
    "enhancing": "Generating materials",
    "saving": "Saving results",
    "complete": "Complete",
}

_executor = ThreadPoolExecutor(max_workers=2)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class PipelineRun:
    run_id: str
    profile: str
    mode: str
    workspace_id: str | None = None
    status: str = "pending"  # pending | running | completed | failed
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress_messages: list[str] = field(default_factory=list)
    jobs_found: int = 0
    jobs_scored: int = 0
    strong_matches: int = 0
    jobs_before_filters: int = 0
    ai_scored_count: int = 0
    keyword_scored_count: int = 0
    funnel: list[dict] = field(default_factory=list)
    error: str | None = None
    queue: asyncio.Queue | None = None
    loop: asyncio.AbstractEventLoop | None = None


# In-memory store of recent runs (capped)
_runs: dict[str, PipelineRun] = {}
_MAX_RUNS = 50


class _ProgressTracker:
    """Wraps the pipeline progress callback to emit structured stage events."""

    def __init__(self, run: PipelineRun, mode: str) -> None:
        self.run = run
        self.stages = _STAGE_WEIGHTS.get(mode, _STAGE_WEIGHTS["search_score"])
        self.current_idx = 0
        self.stage_frac = 0.0  # 0.0–1.0 within current stage
        self.started = time.monotonic()

    @property
    def current_stage(self) -> str:
        if self.current_idx < len(self.stages):
            return self.stages[self.current_idx][0]
        return "complete"

    def __call__(self, msg: str) -> None:
        """Called for every progress message from the pipeline."""
        self.run.progress_messages.append(msg)
        _send_event(self.run, "progress", msg)

        # Detect stage transitions from message text
        lower = msg.lower()
        if ("searching" in lower or "role×location" in lower) and (
            "parallel" in lower or "combo" in lower or "role" in lower
        ):
            self._advance("searching")
        elif "quick-scoring" in lower:
            self._advance("scoring")
        elif "ai-scoring" in lower:
            self._advance("ai_scoring")
        elif "enhancing" in lower and "ai" in lower:
            self._advance("enhancing")
        elif "saving" in lower and "database" in lower:
            self._advance("saving")
        elif "done!" in lower:
            self.current_idx = len(self.stages)
            self.stage_frac = 1.0

        # Extract fractional progress from patterns like [3/50] or "scored 10/25"
        m = re.search(r"\[(\d+)/(\d+)\]", msg)
        if not m:
            m = re.search(r"(\d+)/(\d+)\s+jobs", msg, re.IGNORECASE)
        if not m:
            m = re.search(r"scored\s+(\d+)/(\d+)", msg, re.IGNORECASE)
        if not m:
            m = re.search(r"Enhancing\s+(\d+)/(\d+)", msg)
        if m:
            current, total = int(m.group(1)), int(m.group(2))
            if total > 0:
                self.stage_frac = min(current / total, 1.0)

        self._emit()

    def _advance(self, stage_name: str) -> None:
        for i, (name, _) in enumerate(self.stages):
            if name == stage_name and i >= self.current_idx:
                self.current_idx = i
                self.stage_frac = 0.0
                break

    def _emit(self) -> None:
        pct = 0.0
        for i, (_, weight) in enumerate(self.stages):
            if i < self.current_idx:
                pct += weight
            elif i == self.current_idx:
                pct += weight * self.stage_frac
                break

        elapsed = time.monotonic() - self.started
        _send_event(
            self.run,
            "stage",
            json.dumps({
                "percent": min(round(pct * 100), 99),
                "stage": self.current_stage,
                "stage_label": _STAGE_LABELS.get(self.current_stage, self.current_stage),
                "elapsed": round(elapsed, 1),
            }),
        )


def _cleanup_old_runs() -> None:
    if len(_runs) > _MAX_RUNS:
        oldest = sorted(_runs.values(), key=lambda r: r.started_at or _utcnow())
        for run in oldest[: len(_runs) - _MAX_RUNS]:
            _runs.pop(run.run_id, None)


def _with_db(callback) -> None:
    from app.models.database import get_db

    db_gen = get_db()
    db = next(db_gen)
    try:
        callback(db)
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def _persist_workspace_run_status(
    run: PipelineRun,
    *,
    error: str = "",
) -> None:
    if not run.workspace_id:
        return

    def _callback(db) -> None:
        from app.services import workspace_service

        workspace_service.update_search_run_status(
            db,
            run.run_id,
            status=run.status,
            jobs_found=run.jobs_found,
            jobs_scored=run.jobs_scored,
            strong_matches=run.strong_matches,
            error=error,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )

    try:
        _with_db(_callback)
    except Exception:
        logger.warning("Failed to persist workspace run status", exc_info=True)


def _persist_workspace_event(run: PipelineRun, event_type: str, data: str) -> None:
    if not run.workspace_id:
        return

    def _callback(db) -> None:
        from app.services import workspace_service

        workspace_service.append_search_event(
            db,
            run.workspace_id,
            run.run_id,
            event_type,
            data,
        )

    try:
        _with_db(_callback)
    except Exception:
        logger.warning("Failed to persist workspace run event", exc_info=True)


def _try_start_inline_dev_hosted_run(run: PipelineRun) -> bool:
    """Run hosted searches inline in the local sandbox if no worker is alive."""
    settings = get_settings()
    if not run.workspace_id or not settings.dev_hosted_auth_enabled:
        return False

    claimed = False

    def _callback(db) -> None:
        nonlocal claimed
        from app.services import workspace_service

        if workspace_service.list_recent_worker_heartbeats(
            db,
            expected_release=settings.resolved_app_release,
        ):
            return

        record = workspace_service.claim_search_run(db, run.run_id, "sandbox-inline")
        if not record:
            return

        run.status = "running"
        run.started_at = _coerce_utc(record.started_at)
        claimed = True

    try:
        _with_db(_callback)
    except Exception:
        logger.warning("Failed to check hosted worker availability", exc_info=True)
        return False

    return claimed


def _has_compatible_hosted_worker() -> bool:
    compatible = False
    settings = get_settings()

    def _callback(db) -> None:
        nonlocal compatible
        from app.services import workspace_service

        compatible = bool(
            workspace_service.list_recent_worker_heartbeats(
                db,
                expected_release=settings.resolved_app_release,
            )
        )

    try:
        _with_db(_callback)
    except Exception:
        logger.warning("Failed to inspect worker heartbeats", exc_info=True)
        return False

    return compatible


def start_run(
    *,
    roles: list[str],
    locations: list[str],
    keywords: list[str],
    companies: list[str] | None = None,
    include_remote: bool,
    workplace_preference: str = "remote_friendly",
    max_days_old: int,
    use_ai: bool,
    profile: str,
    mode: str,
    loop: asyncio.AbstractEventLoop,
    workspace_id: str | None = None,
    config_override: dict | None = None,
    llm_override: Any | None = None,
    snapshot=None,
) -> PipelineRun:
    """Launch a pipeline run in a background thread. Returns immediately.

    Idempotent for in-progress runs: if a search is already active for the
    same workspace, return the existing PipelineRun instead of starting a
    new one. The frontend's activate() flow picks up its run_id and shows
    the in-progress search seamlessly — no scary "search already running"
    toast on a page refresh + re-click.

    Concurrent scrape prevention (rate limits, duplicate results) is
    preserved: the second caller doesn't actually start a second worker.
    """
    # Guard against concurrent runs for the same workspace — but return
    # the existing run rather than raising. The user clicking Run a second
    # time should land them on the in-progress search, not get an error.
    if workspace_id:
        for existing in _runs.values():
            if (
                existing.workspace_id == workspace_id
                and existing.status in ("pending", "running")
            ):
                logger.info(
                    "Search already in progress for workspace %s; returning existing run %s",
                    workspace_id, existing.run_id,
                )
                return existing

    run_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue | None = asyncio.Queue() if not get_settings().hosted_mode else None

    # The run's workspace_id is IDENTITY: run persistence, events, resume,
    # prefs. Saved ROWS scope per workspace only in hosted mode; local and
    # desktop runs write into the one shared pool (workspace_id NULL) the
    # board reads, no matter which session started them.
    data_workspace_id = workspace_id if get_settings().hosted_mode else None
    if config_override and isinstance(config_override.get("workspace"), dict):
        config_override = {
            **config_override,
            "workspace": {**config_override["workspace"], "workspace_id": data_workspace_id},
        }

    run = PipelineRun(
        run_id=run_id,
        profile=profile,
        mode=mode,
        workspace_id=workspace_id,
        status="pending",
        queue=queue,
        loop=loop,
    )
    if not get_settings().hosted_mode:
        _cleanup_old_runs()
        _runs[run_id] = run

    request_payload = {
        "roles": roles,
        "locations": locations,
        "keywords": keywords,
        "companies": companies or [],
        "include_remote": include_remote,
        "workplace_preference": workplace_preference,
        "max_days_old": max_days_old,
        "use_ai": use_ai,
        "profile": profile,
        "mode": mode,
    }

    if workspace_id and snapshot is not None:
        def _callback(db) -> None:
            from app.services import workspace_service

            workspace_service.register_search_run(
                db,
                workspace_id,
                run.run_id,
                run.status,
                run.mode,
                snapshot,
                run.started_at,
                request_payload=request_payload,
            )

        _with_db(_callback)

    if get_settings().hosted_mode and workspace_id:
        if _try_start_inline_dev_hosted_run(run):
            _send_event(run, "progress", "Hosted sandbox worker unavailable - running inline for local development")
            _emit_stage_event(run, stage="searching", percent=2, label="Starting search")
        else:
            if not _has_compatible_hosted_worker():
                raise RuntimeError(
                    f"No compatible hosted worker is ready for release {get_settings().resolved_app_release}"
                )
            _send_event(run, "progress", "Queued - waiting for an available worker")
            _emit_stage_event(run, stage="queued", percent=1)
            return run

    # Merge keywords into roles for SEARCH, but only title-shaped keywords —
    # pure skills ("rbac", "dbt", "sox compliance", "pii masking") return noise
    # as board job-title queries and burn the board's limited query budget.
    # The full keyword list still drives scoring (passed via the run payload).
    from job_finder.pipeline import _is_searchable_title
    all_roles = list(roles)
    if keywords:
        all_roles.extend(k for k in keywords if _is_searchable_title(k))

    effective_locations = list(locations)
    if workplace_preference == "remote_only":
        effective_locations = ["Remote"]
    elif include_remote and "Remote" not in effective_locations:
        effective_locations = list(effective_locations) + ["Remote"]

    _executor.submit(
        _execute_pipeline,
        run,
        all_roles,
        effective_locations,
        use_ai,
        mode,
        workplace_preference,
        max_days_old,
        workspace_id,
        config_override or {},
        llm_override,
        companies or [],
        True,
        data_workspace_id,
    )
    return run


def _execute_pipeline(
    run: PipelineRun,
    roles: list[str],
    locations: list[str],
    use_ai: bool,
    mode: str,
    workplace_preference: str = "remote_friendly",
    max_days_old: int | None = None,
    workspace_id: str | None = None,
    config_override: dict | None = None,
    llm_override: Any | None = None,
    target_companies: list[str] | None = None,
    emit_error_event: bool = True,
    data_workspace_id: str | None = None,
) -> None:
    """Run the pipeline in a worker thread."""
    run.status = "running"
    run.started_at = _coerce_utc(run.started_at) or _utcnow()
    _persist_workspace_run_status(run)

    # Report only the sources actually in use, not the full plugin registry.
    # Without this filter, the "searching N sources" line lies — it lists
    # every registered scraper even when the user has disabled most of them.
    try:
        from job_finder.tools.scrapers import get_registry
        from job_finder.pipeline import _load_search_config
        _cfg = _load_search_config(run.profile)
        _registry = get_registry()
        _enabled_names: list[str] = []
        for _board in _cfg.get("job_boards", []) or []:
            _key = str(_board).strip().lower()
            if _key in _registry:
                _enabled_names.append(_registry[_key].display_name)
        for _entry in _cfg.get("additional_sources", []) or []:
            if not isinstance(_entry, dict) or not _entry.get("enabled"):
                continue
            _key = str(_entry.get("name", "")).strip().lower()
            if _key in _registry:
                _enabled_names.append(_registry[_key].display_name)
        active_source_count = len(_enabled_names)
        source_names = ", ".join(_enabled_names) if _enabled_names else "multiple sources"
    except Exception:
        active_source_count = 0
        source_names = "multiple sources"
    mode_label = _MODE_LABELS.get(mode, mode)
    _send_event(run, "progress", f"{mode_label} started — searching {active_source_count or 'multiple'} sources: {source_names}")
    _send_event(run, "progress", f"Searching {len(roles)} terms across {len(locations)} locations")

    try:
        pipeline = get_pipeline(profile=run.profile)
        if llm_override is not None:
            pipeline.llm = llm_override if getattr(llm_override, "is_configured", False) else None
        if config_override:
            for key, value in config_override.items():
                if isinstance(value, dict) and isinstance(pipeline.config.get(key), dict):
                    merged = dict(pipeline.config.get(key, {}))
                    merged.update(value)
                    pipeline.config[key] = merged
                else:
                    pipeline.config[key] = value

        # ── AI Company Discovery ─────────────────────────────────
        # If the LLM is available and we have a resume, ask it to discover
        # companies at search time — not just keyword-blast job boards.
        # This is what makes the search smarter than a basic aggregator:
        # the LLM reasons about which companies would want THIS person
        # based on their full background, not just role title keywords.
        if (
            pipeline.llm
            and pipeline.llm.is_configured
            and use_ai
            and (pipeline.config.get("search_settings") or {}).get("ai_company_discovery", True)
        ):
            _send_event(run, "progress", "AI is discovering companies that match your background...")
            discovered_companies = _ai_discover_companies(
                pipeline, roles, target_companies or [], run,
            )
            if discovered_companies:
                if target_companies is None:
                    target_companies = []
                existing_lower = {c.lower() for c in target_companies}
                for name in discovered_companies:
                    if name.lower() not in existing_lower:
                        target_companies.append(name)
                        existing_lower.add(name.lower())

        # Inject AI-suggested target companies into the pipeline config, but
        # only after ATS discovery confirms which board each company actually
        # uses. This avoids blasting guessed slugs at every ATS API.
        if target_companies:
            from app.services.watchlist_service import build_watchlist_entries
            existing = pipeline.config.get("watchlist", [])
            existing_keys = {
                (str(entry.get("name", "")).lower(), str(entry.get("ats", "")))
                for entry in existing
                if isinstance(entry, dict)
            }
            discovered = build_watchlist_entries(target_companies)
            for entry in discovered:
                key = (str(entry.get("name", "")).lower(), str(entry.get("ats", "")))
                if key in existing_keys:
                    continue
                existing.append(entry)
                existing_keys.add(key)
            pipeline.config["watchlist"] = existing
            logger.info(
                "Injected %d confirmed ATS company targets from %d AI-suggested companies",
                len(discovered),
                len(target_companies),
            )
            _send_event(run, "progress", f"Targeting {len(target_companies)} companies from resume analysis")

        # Load workspace resume — MUST succeed in workspace mode to prevent
        # cross-user data leaks via shared filesystem fallback.
        if workspace_id:
            from app.dependencies import get_db
            from app.services import workspace_service
            db = next(get_db())
            try:
                resume_text = workspace_service.get_resume_text(db, workspace_id)
                if resume_text:
                    pipeline.set_resume_text(resume_text)
                    logger.info("Loaded workspace resume for %s (%d chars)", workspace_id, len(resume_text))
            finally:
                db.close()
            # Block file-based fallback regardless — workspace pipelines must
            # never read from the shared knowledge/ directory.
            pipeline.require_preloaded_resume()

        if max_days_old is not None:
            pipeline.config.setdefault("search_settings", {})["max_days_old"] = max_days_old

        from job_finder.company_classifier import parse_location

        existing_loc_prefs = dict(pipeline.config.get("location_preferences", {}))

        preferred_locations = list(existing_loc_prefs.get("preferred_locations", [])) or [
            location for location in locations
            if location.strip().lower() not in {"remote", "anywhere", "united states", "usa", "us"}
        ]
        preferred_states: list[str] = list(existing_loc_prefs.get("preferred_states", []))
        preferred_cities: list[str] = list(existing_loc_prefs.get("preferred_cities", []))
        if not preferred_states or not preferred_cities:
            for location in preferred_locations:
                parsed = parse_location(location)
                if parsed.get("state") and parsed["state"] not in preferred_states:
                    preferred_states.append(parsed["state"])
                if parsed.get("city") and parsed["city"] not in preferred_cities:
                    preferred_cities.append(parsed["city"])

        pipeline.config["locations"] = list(locations)
        updated_location_preferences = dict(existing_loc_prefs)
        updated_location_preferences.update({
            "filter_enabled": bool(preferred_locations or existing_loc_prefs.get("preferred_places")) or workplace_preference != "remote_friendly",
            "preferred_locations": preferred_locations,
            "preferred_states": preferred_states,
            "preferred_cities": preferred_cities,
            "remote_only": workplace_preference == "remote_only",
            "include_remote": workplace_preference != "location_only",
            "workplace_preference": workplace_preference,
        })
        pipeline.config["location_preferences"] = updated_location_preferences

        tracker = _ProgressTracker(run, mode)
        progress_cb = tracker

        if mode == "search_only":
            jobs = pipeline.search_all_jobs(
                roles=roles, locations=locations, progress=progress_cb
            )
            run.jobs_found = len(jobs) if jobs else 0
            run.funnel = list(getattr(pipeline, '_last_funnel', []) or [])
            run.jobs_before_filters = getattr(pipeline, '_last_pre_filter_count', run.jobs_found)
            # Save to DB
            if jobs:
                _save_search_results(
                    pipeline,
                    jobs,
                    progress_cb,
                    search_run_id=run.run_id,
                    workspace_id=data_workspace_id,
                )
        else:
            # search_score: AI scoring only (no enhancement)
            # full_pipeline: AI scoring + enhancement (resume tweaks, cover letters)
            jobs = pipeline.run_full_pipeline(
                progress=progress_cb,
                roles=roles,
                locations=locations,
                use_ai=use_ai,
                enhance=(mode == "full_pipeline"),
                search_run_id=run.run_id,
            )
            run.jobs_found = len(jobs) if jobs else 0
            run.jobs_before_filters = getattr(pipeline, '_last_pre_filter_count', run.jobs_found)
            run.funnel = list(getattr(pipeline, '_last_funnel', []) or [])
            run.jobs_scored = sum(1 for j in (jobs or []) if j.get("overall_score") is not None)
            run.ai_scored_count = sum(
                1 for j in (jobs or [])
                if j.get("scoring_method") == "ai" or (
                    j.get("score_reasoning") and "AI intel" in str(j.get("score_reasoning", ""))
                )
            )
            run.keyword_scored_count = run.jobs_scored - run.ai_scored_count
            strong_threshold = pipeline.config.get("scoring", {}).get("thresholds", {}).get("strong_apply", 70)
            run.strong_matches = sum(
                1 for j in (jobs or [])
                if (j.get("overall_score") or 0) >= strong_threshold
            )

        # Auto-merge any cross-source duplicates in the DB
        merged = _auto_deduplicate(pipeline.profile_name, workspace_id=data_workspace_id)
        if merged > 0:
            _send_event(run, "progress", f"Merged {merged} cross-source duplicates")

        # Auto-check URLs to mark dead postings. Runs in the background
        # after scoring so the user sees results immediately while expired
        # jobs are quietly flagged.
        if jobs and workspace_id:
            try:
                _send_event(run, "progress", "Checking which job postings are still active...")
                from app.services.application_service import check_urls as _check_urls
                # Cover this run's jobs (capped); parallelized inside check_urls.
                _limit = min(max(len(jobs), 50), 200)
                _with_db(lambda db: _check_urls(db, limit=_limit, workspace_id=data_workspace_id))
            except Exception as exc:
                logger.debug("Auto URL check failed (non-fatal): %s", exc)

        # Count jobs by source
        sources: dict[str, int] = {}
        if jobs:
            for j in jobs:
                src = j.get("source", "unknown") or "unknown"
                sources[src] = sources.get(src, 0) + 1

        run.status = "completed"
        run.completed_at = _utcnow()
        duration = (run.completed_at - (_coerce_utc(run.started_at) or run.completed_at)).total_seconds()
        _send_event(
            run,
            "complete",
            json.dumps({
                "jobs_found": run.jobs_found,
                "jobs_before_filters": run.jobs_before_filters,
                "jobs_scored": run.jobs_scored,
                "strong_matches": run.strong_matches,
                "ai_scored_count": run.ai_scored_count,
                "keyword_scored_count": run.keyword_scored_count,
                "duration_seconds": round(duration, 1),
                "sources": sources,
            }),
        )
        _persist_workspace_run_status(run)
    except Exception as e:
        logger.exception("Pipeline run %s failed", run.run_id)
        run.status = "failed"
        run.error = str(e)
        run.completed_at = _utcnow()
        if emit_error_event:
            _send_event(run, "error", str(e))
        _persist_workspace_run_status(run, error=str(e))


def _ai_discover_companies(
    pipeline: Any,
    roles: list[str],
    existing_companies: list[str],
    run: PipelineRun,
) -> list[str]:
    """Use the LLM to discover companies at search time.

    This is the key differentiator vs basic job board aggregation.
    Instead of just keyword-blasting Indeed/LinkedIn, we ask the LLM:
    "Given this resume and these target roles, which specific companies
    are likely hiring and would be a strong fit?"

    The LLM can reason about industry overlap, tech stack alignment,
    company stage, and culture — things keyword search can't do.
    """
    if not pipeline.llm or not pipeline.llm.is_configured:
        return []

    resume_text = getattr(pipeline, '_preloaded_resume_text', None) or ""
    if not resume_text:
        return []

    # Truncate resume for speed
    resume_snippet = resume_text[:3000]
    existing_str = ", ".join(existing_companies[:20]) if existing_companies else "none yet"

    prompt = f"""Based on this resume, suggest 20-30 SPECIFIC companies that are likely hiring for these roles and would be a strong fit for this candidate.

Roles: {', '.join(roles[:8])}
Already targeting: {existing_str}

Think about:
- Companies with matching tech stack (check the resume's tools/frameworks)
- Companies at the right stage for this person's seniority
- Companies in adjacent industries that hire similar roles
- Growing companies that are actively hiring
- Include niche/emerging companies, not just FAANG

Return ONLY a JSON array of company names. No explanations.
Example: ["Databricks", "Snowflake", "Fivetran", "dbt Labs"]

Resume:
{resume_snippet}"""

    try:
        result = pipeline.llm.chat_json(
            "You are a career advisor. Return only valid JSON.",
            prompt,
            max_tokens=1024,
            temperature=0.3,
        )
        if isinstance(result, list):
            companies = [str(c).strip() for c in result if isinstance(c, str) and c.strip()]
            if companies:
                _send_event(run, "progress", f"AI discovered {len(companies)} companies to check: {', '.join(companies[:10])}...")
                return companies
        elif isinstance(result, dict) and "companies" in result:
            companies = [str(c).strip() for c in result["companies"] if isinstance(c, str)]
            if companies:
                _send_event(run, "progress", f"AI discovered {len(companies)} companies to check")
                return companies
    except Exception as exc:
        logger.warning("AI company discovery failed: %s", exc)
        _send_event(run, "progress", "AI company discovery skipped (will use job boards only)")

    return []


def _auto_deduplicate(profile: str | None = None, workspace_id: str | None = None) -> int:
    """Merge cross-source duplicates in the DB after a pipeline run."""
    try:
        from job_finder.pipeline import _normalize_company, _normalize_title
        from app.models.application import ApplicationRecord
        from app.models.database import get_db

        session_gen = get_db()
        session = next(session_gen)
        try:
            query = session.query(ApplicationRecord)
            if workspace_id:
                query = query.filter(ApplicationRecord.workspace_id == workspace_id)
            elif profile:
                query = query.filter(ApplicationRecord.profile == profile)
            all_records = query.all()

            groups: dict[str, list] = {}
            for rec in all_records:
                co = _normalize_company(rec.company or "")
                ti = _normalize_title(rec.job_title or "")
                if not co or not ti:
                    continue
                key = f"{co}||{ti}"
                groups.setdefault(key, []).append(rec)

            removed = 0
            for group in groups.values():
                if len(group) <= 1:
                    continue
                # Keep richest record
                group.sort(
                    key=lambda r: (
                        1 if r.status and r.status != "found" else 0,
                        1 if r.cover_letter else 0,
                        1 if r.company_intel_json else 0,
                        1 if (r.salary_min or r.salary_max) else 0,
                        r.overall_score or 0,
                        len(r.description or ""),
                    ),
                    reverse=True,
                )
                keeper = group[0]
                for dup in group[1:]:
                    if not keeper.salary_min and dup.salary_min:
                        keeper.salary_min = dup.salary_min
                    if not keeper.salary_max and dup.salary_max:
                        keeper.salary_max = dup.salary_max
                    if not keeper.cover_letter and dup.cover_letter:
                        keeper.cover_letter = dup.cover_letter
                    if not keeper.company_intel_json and dup.company_intel_json:
                        keeper.company_intel_json = dup.company_intel_json
                    if dup.overall_score and (not keeper.overall_score or dup.overall_score > keeper.overall_score):
                        keeper.overall_score = dup.overall_score
                        keeper.technical_score = dup.technical_score
                        keeper.leadership_score = dup.leadership_score
                        keeper.platform_building_score = dup.platform_building_score
                        keeper.comp_potential_score = dup.comp_potential_score
                        keeper.company_trajectory_score = dup.company_trajectory_score
                        keeper.culture_fit_score = dup.culture_fit_score
                        keeper.career_progression_score = dup.career_progression_score
                        keeper.recommendation = dup.recommendation
                        keeper.score_reasoning = dup.score_reasoning
                        keeper.key_strengths = dup.key_strengths
                        keeper.key_gaps = dup.key_gaps
                    if len(dup.description or "") > len(keeper.description or ""):
                        keeper.description = dup.description
                    session.delete(dup)
                    removed += 1
            if removed > 0:
                session.commit()
            return removed
        finally:
            try:
                next(session_gen)
            except StopIteration:
                pass
    except Exception:
        logger.warning("Auto-dedup failed", exc_info=True)
        return 0


def _save_search_results(
    pipeline,
    jobs: list[dict],
    progress_cb,
    search_run_id: str | None = None,
    workspace_id: str | None = None,
) -> None:
    """Save search-only results to DB (mirrors app.py search_only logic)."""
    import json as _json
    from job_finder.models.database import init_db, save_application
    from job_finder.company_classifier import classify_company, classify_work_type

    init_db()
    progress_cb("Saving results to database...")
    for job in jobs:
        ct = classify_company(
            job.get("company", ""),
            job.get("funding_stage"),
            job.get("total_funding"),
            job.get("employee_count"),
        )
        job["company_type"] = ct
        wt = job.get("work_type") or classify_work_type(
            job.get("location", ""),
            job.get("description", ""),
            job.get("is_remote", False),
        )
        job["work_type"] = wt
        save_application(
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            job_url=job.get("url", "") or None,
            source=job.get("source", ""),
            description=job.get("description", ""),
            is_remote=job.get("is_remote", False),
            salary_min=job.get("salary_min"),
            salary_max=job.get("salary_max"),
            profile=pipeline.profile_name,
            company_type=ct,
            work_type=wt,
            search_run_id=search_run_id,
            workspace_id=workspace_id,
            date_posted=job.get("date_posted"),
            date_confidence=job.get("date_confidence"),
        )
    progress_cb(f"Saved {len(jobs)} jobs to database")


def _send_event(run: PipelineRun, event_type: str, data: str) -> None:
    """Thread-safe: push an SSE event onto the run's asyncio queue."""
    _persist_workspace_event(run, event_type, data)
    if run.queue and run.loop:
        try:
            asyncio.run_coroutine_threadsafe(
                run.queue.put({"event": event_type, "data": data}),
                run.loop,
            )
        except RuntimeError:
            pass  # loop closed


def _emit_stage_event(
    run: PipelineRun,
    *,
    stage: str,
    percent: int,
    elapsed: float = 0.0,
    label: str | None = None,
) -> None:
    _send_event(
        run,
        "stage",
        json.dumps({
            "percent": percent,
            "stage": stage,
            "stage_label": label or _STAGE_LABELS.get(stage, stage),
            "elapsed": round(elapsed, 1),
        }),
    )


def process_next_hosted_run(worker_id: str | None = None) -> bool:
    """Claim and execute one hosted search run from durable storage."""
    if not get_settings().hosted_mode:
        return False

    from app.models.database import get_db
    from app.services import workspace_service

    effective_worker_id = worker_id or get_settings().worker_id or f"worker-{os.getpid()}"
    db_gen = get_db()
    db = next(db_gen)
    try:
        record = workspace_service.claim_next_search_run(db, effective_worker_id)
        if not record:
            return False

        payload = workspace_service.get_search_request_payload(record)
        payload_roles = [str(item) for item in payload.get("roles") or []]
        payload_keywords = [str(item) for item in payload.get("keywords") or []]
        run = PipelineRun(
            run_id=record.run_id,
            profile=str(payload.get("profile") or "workspace"),
            mode=record.mode or str(payload.get("mode") or "search_score"),
            workspace_id=record.workspace_id,
            status="running",
            started_at=_coerce_utc(record.started_at),
        )
        _send_event(run, "progress", "Worker claimed run - starting search")
        _emit_stage_event(run, stage="searching", percent=3)

        prefs = workspace_service.get_workspace_preferences(db, record.workspace_id)
        # The queue snapshot is the immutable intent for this run. Preferences
        # may change while a run waits for a worker, and using the live row here
        # would make sourcing terms and the primary-role gate disagree.
        try:
            from app.schemas.workspace import SearchSnapshot

            snapshot = SearchSnapshot.model_validate_json(record.snapshot_json or "{}")
            prefs = type(prefs).model_validate(
                {**prefs.model_dump(), **snapshot.model_dump()}
            )
        except Exception:
            logger.warning("Invalid search snapshot for run %s; using current preferences", record.run_id)
        llm = workspace_service.get_workspace_llm(db, record.workspace_id, fallback_to_global=True)
        config_override = workspace_service.build_pipeline_config_override(prefs, record.workspace_id)

        from job_finder.pipeline import _is_searchable_title
        _execute_pipeline(
            run,
            roles=payload_roles + [k for k in payload_keywords if _is_searchable_title(k)],
            locations=[str(item) for item in payload.get("locations") or []],
            use_ai=bool(payload.get("use_ai")),
            mode=run.mode,
            workplace_preference=str(payload.get("workplace_preference") or "remote_friendly"),
            max_days_old=int(payload.get("max_days_old") or prefs.max_days_old or 14),
            workspace_id=record.workspace_id,
            config_override=config_override,
            llm_override=llm,
            target_companies=[str(item) for item in payload.get("companies") or []],
            emit_error_event=False,
            # hosted-only path: rows belong to the visitor's workspace
            data_workspace_id=record.workspace_id,
        )

        db.refresh(record)
        if run.status == "failed" and int(record.attempt_count or 0) < int(record.max_attempts or 1):
            retry_seconds = min(
                get_settings().worker_retry_base_seconds * max(int(record.attempt_count or 1), 1),
                300,
            )
            workspace_service.append_search_event(
                db,
                record.workspace_id,
                record.run_id,
                "progress",
                f"Run failed, retrying in {retry_seconds} seconds",
            )
            workspace_service.release_search_run_for_retry(
                db,
                record.run_id,
                error=run.error or "Retry scheduled",
                retry_seconds=retry_seconds,
            )
            return True

        if run.status == "failed":
            workspace_service.append_search_event(
                db,
                record.workspace_id,
                record.run_id,
                "error",
                run.error or "Search failed",
            )
        return True
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


async def stream_progress(run_id: str):
    """Async generator yielding SSE-formatted strings."""
    run = _runs.get(run_id)
    if not run:
        yield f"event: error\ndata: Run {run_id} not found\n\n"
        return

    # Replay existing messages
    for msg in list(run.progress_messages):
        yield f"event: progress\ndata: {msg}\n\n"

    if run.status in ("completed", "failed"):
        if run.error:
            yield f"event: error\ndata: {run.error}\n\n"
        else:
            yield f"event: complete\ndata: done\n\n"
        return

    # Stream live events
    while True:
        try:
            event = await asyncio.wait_for(run.queue.get(), timeout=60.0)
            yield f"event: {event['event']}\ndata: {event['data']}\n\n"
            if event["event"] in ("complete", "error"):
                return
        except asyncio.TimeoutError:
            yield "event: ping\ndata: keepalive\n\n"
            if run.status in ("completed", "failed"):
                return


async def stream_persisted_progress(workspace_id: str, run_id: str):
    """Async generator yielding SSE-formatted strings from persisted hosted runs."""
    from app.models.database import get_db
    from app.services import workspace_service

    last_event_id = 0
    while True:
        db_gen = get_db()
        db = next(db_gen)
        try:
            run = workspace_service.get_search_run(db, workspace_id, run_id)
            if not run:
                yield f"event: error\ndata: Run {run_id} not found\n\n"
                return

            events = workspace_service.list_search_events(
                db,
                workspace_id,
                run_id,
                after_id=last_event_id,
            )
            for event in events:
                last_event_id = event.id
                yield f"event: {event.event_type}\ndata: {event.payload}\n\n"

            if run.status in ("completed", "failed") and not events:
                return
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        await asyncio.sleep(0.5)


def get_run(run_id: str) -> PipelineRun | None:
    return _runs.get(run_id)


def list_runs(limit: int = 20, workspace_id: str | None = None) -> list[PipelineRun]:
    runs = list(_runs.values())
    if workspace_id is not None:
        runs = [run for run in runs if run.workspace_id == workspace_id]
    runs = sorted(runs, key=lambda r: r.started_at or _utcnow(), reverse=True)
    return runs[:limit]
