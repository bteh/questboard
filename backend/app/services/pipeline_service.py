"""Pipeline execution service with thread-based concurrency and SSE progress."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

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

_STRONG_MATCH_THRESHOLD = 55

_STAGE_LABELS: dict[str, str] = {
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


@dataclass
class PipelineRun:
    run_id: str
    profile: str
    mode: str
    status: str = "pending"  # pending | running | completed | failed
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress_messages: list[str] = field(default_factory=list)
    jobs_found: int = 0
    jobs_scored: int = 0
    strong_matches: int = 0
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


def start_run(
    *,
    roles: list[str],
    locations: list[str],
    keywords: list[str],
    include_remote: bool,
    max_days_old: int,
    use_ai: bool,
    profile: str,
    mode: str,
    loop: asyncio.AbstractEventLoop,
) -> PipelineRun:
    """Launch a pipeline run in a background thread. Returns immediately."""
    _cleanup_old_runs()

    run_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue = asyncio.Queue()
    run = PipelineRun(
        run_id=run_id,
        profile=profile,
        mode=mode,
        status="pending",
        queue=queue,
        loop=loop,
    )
    _runs[run_id] = run

    # Merge keywords into roles for search (pipeline treats them similarly)
    all_roles = list(roles)
    if keywords:
        all_roles.extend(keywords)

    if include_remote and "Remote" not in locations:
        locations = list(locations) + ["Remote"]

    _executor.submit(
        _execute_pipeline,
        run,
        all_roles,
        locations,
        use_ai,
        mode,
    )
    return run


def _execute_pipeline(
    run: PipelineRun,
    roles: list[str],
    locations: list[str],
    use_ai: bool,
    mode: str,
) -> None:
    """Run the pipeline in a worker thread."""
    run.status = "running"
    run.started_at = _utcnow()

    try:
        from job_finder.tools.scrapers import get_all_metadata
        all_sources = get_all_metadata()
        source_names = ", ".join(m.display_name for m in all_sources)
    except Exception:
        all_sources = []
        source_names = "multiple sources"
    mode_label = _MODE_LABELS.get(mode, mode)
    _send_event(run, "progress", f"{mode_label} started — searching {len(all_sources) or 'multiple'} sources: {source_names}")
    _send_event(run, "progress", f"Searching {len(roles)} terms across {len(locations)} locations")

    try:
        pipeline = get_pipeline(profile=run.profile)

        tracker = _ProgressTracker(run, mode)
        progress_cb = tracker

        if mode == "search_only":
            jobs = pipeline.search_all_jobs(
                roles=roles, locations=locations, progress=progress_cb
            )
            run.jobs_found = len(jobs) if jobs else 0
            # Save to DB
            if jobs:
                _save_search_results(pipeline, jobs, progress_cb)
        else:
            # search_score: AI scoring only (no enhancement)
            # full_pipeline: AI scoring + enhancement (resume tweaks, cover letters)
            jobs = pipeline.run_full_pipeline(
                progress=progress_cb,
                roles=roles,
                locations=locations,
                use_ai=use_ai,
                enhance=(mode == "full_pipeline"),
            )
            run.jobs_found = len(jobs) if jobs else 0
            run.jobs_scored = sum(1 for j in (jobs or []) if j.get("overall_score") is not None)
            run.strong_matches = sum(
                1 for j in (jobs or [])
                if (j.get("overall_score") or 0) >= _STRONG_MATCH_THRESHOLD
            )

        # Auto-merge any cross-source duplicates in the DB
        merged = _auto_deduplicate(pipeline.profile_name)
        if merged > 0:
            _send_event(run, "progress", f"Merged {merged} cross-source duplicates")

        # Count jobs by source
        sources: dict[str, int] = {}
        if jobs:
            for j in jobs:
                src = j.get("source", "unknown") or "unknown"
                sources[src] = sources.get(src, 0) + 1

        run.status = "completed"
        run.completed_at = _utcnow()
        duration = (run.completed_at - run.started_at).total_seconds()
        _send_event(
            run,
            "complete",
            json.dumps({
                "jobs_found": run.jobs_found,
                "jobs_scored": run.jobs_scored,
                "strong_matches": run.strong_matches,
                "duration_seconds": round(duration, 1),
                "sources": sources,
            }),
        )
    except Exception as e:
        logger.exception("Pipeline run %s failed", run.run_id)
        run.status = "failed"
        run.error = str(e)
        run.completed_at = _utcnow()
        _send_event(run, "error", str(e))


def _auto_deduplicate(profile: str | None = None) -> int:
    """Merge cross-source duplicates in the DB after a pipeline run."""
    try:
        from job_finder.pipeline import _normalize_company, _normalize_title
        from app.models.application import ApplicationRecord
        from app.models.database import get_db

        session = next(get_db())
        try:
            query = session.query(ApplicationRecord)
            if profile:
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
            session.close()
    except Exception:
        logger.warning("Auto-dedup failed", exc_info=True)
        return 0


def _save_search_results(pipeline, jobs: list[dict], progress_cb) -> None:
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
        )
    progress_cb(f"Saved {len(jobs)} jobs to database")


def _send_event(run: PipelineRun, event_type: str, data: str) -> None:
    """Thread-safe: push an SSE event onto the run's asyncio queue."""
    if run.queue and run.loop:
        try:
            asyncio.run_coroutine_threadsafe(
                run.queue.put({"event": event_type, "data": data}),
                run.loop,
            )
        except RuntimeError:
            pass  # loop closed


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


def get_run(run_id: str) -> PipelineRun | None:
    return _runs.get(run_id)


def list_runs(limit: int = 20) -> list[PipelineRun]:
    runs = sorted(_runs.values(), key=lambda r: r.started_at or _utcnow(), reverse=True)
    return runs[:limit]
