"""Background scheduler — checks every 60s for due scheduled searches.

No external dependencies; uses a simple daemon thread + SQLite.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def start_scheduler() -> None:
    """Start the background scheduler thread (idempotent)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="job-scheduler")
    _thread.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    """Signal the scheduler to stop."""
    _stop_event.set()
    logger.info("Scheduler stopping")


def _loop() -> None:
    """Main scheduler loop — wakes every 60s."""
    while not _stop_event.wait(60):
        try:
            _tick()
        except Exception:
            logger.exception("Scheduler tick failed")


def _tick() -> None:
    """Check for and execute any due schedules."""
    from app.models.database import get_db
    from app.models.schedule import Schedule

    # Keep generator alive so the session isn't prematurely closed by GC
    gen = get_db()
    db = next(gen)
    try:
        now = _utcnow()
        due = (
            db.query(Schedule)
            .filter(
                Schedule.enabled == True,  # noqa: E712
                (Schedule.next_run_at == None) | (Schedule.next_run_at <= now),  # noqa: E711
            )
            .all()
        )
        for sched in due:
            try:
                _run_scheduled(sched, db)
            except Exception:
                logger.exception(
                    "Scheduled run failed for profile %s", sched.profile
                )
                # Still advance next_run_at so we don't retry every 60s
                sched.last_run_at = now
                sched.next_run_at = now + timedelta(hours=sched.interval_hours)
                db.commit()
    finally:
        # Close the generator properly (triggers session.close() in get_db)
        gen.close()


def _run_scheduled(sched, db) -> None:
    """Execute one scheduled pipeline run."""
    from app.dependencies import get_pipeline

    logger.info(
        "Running scheduled search for profile %s (mode=%s, interval=%sh)",
        sched.profile,
        sched.mode,
        sched.interval_hours,
    )

    pipeline = get_pipeline(profile=sched.profile)
    config = pipeline.config
    roles = config.get("target_roles", [])
    locations = config.get("locations", ["Remote"])

    now = _utcnow()

    if sched.mode == "search_only":
        jobs = pipeline.search_all_jobs(roles=roles, locations=locations)
        # Save results to DB (mirrors pipeline_service._save_search_results)
        if jobs:
            from job_finder.company_classifier import classify_company
            from job_finder.models.database import init_db, save_application

            init_db()
            for job in jobs:
                ct = classify_company(
                    job.get("company", ""),
                    job.get("funding_stage"),
                    job.get("total_funding"),
                    job.get("employee_count"),
                )
                job["company_type"] = ct
                save_application(
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                    location=job.get("location", ""),
                    job_url=job.get("url", ""),
                    source=job.get("source", ""),
                    description=job.get("description", ""),
                    is_remote=job.get("is_remote", False),
                    salary_min=job.get("salary_min"),
                    salary_max=job.get("salary_max"),
                    profile=pipeline.profile_name,
                    company_type=ct,
                )
    else:
        use_ai = sched.mode == "full_pipeline"
        jobs = pipeline.run_full_pipeline(
            roles=roles, locations=locations, use_ai=use_ai
        )

    total = len(jobs) if jobs else 0

    sched.last_run_at = now
    sched.next_run_at = now + timedelta(hours=sched.interval_hours)
    sched.last_run_jobs_found = total
    sched.last_run_new_jobs = total
    db.commit()

    logger.info(
        "Scheduled run complete: %d jobs found for profile %s",
        total,
        sched.profile,
    )
