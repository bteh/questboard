import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.dependencies import _src_dir  # noqa: F401 — ensures src/ is on sys.path
from app.api.router import api_router
from app.models.database import get_db, init_db
from app.services import workspace_service

_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


def _get_cors_origins() -> list[str]:
    """Read CORS origins from CORS_ORIGINS env var (comma-separated) or use defaults."""
    raw = os.environ.get("CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return _DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    os.environ["DATABASE_URL"] = settings.resolved_database_url
    os.environ["JOB_FINDER_DATABASE_URL"] = settings.resolved_database_url
    os.environ["JOB_FINDER_DATA_DIR"] = settings.data_dir
    os.environ["JOB_FINDER_MANAGE_SCHEMA"] = "true" if settings.should_manage_schema_on_startup else "false"
    init_db()
    db_gen = get_db()
    try:
        db = next(db_gen)
        workspace_service.cleanup_expired_workspaces(db)
        if not settings.hosted_mode:
            recovered = workspace_service.recover_abandoned_local_search_runs(db)
            if recovered["recovered"] or recovered["failed"]:
                import logging

                logging.getLogger(__name__).info(
                    "Recovered %d interrupted desktop searches; %d exhausted",
                    recovered["recovered"],
                    recovered["failed"],
                )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    from app.services.scheduler_service import build_scheduler

    scheduler = build_scheduler()
    app.state.scheduler = scheduler
    if scheduler is not None:
        scheduler.start()
    from app.services.search_run_worker import build_desktop_search_worker

    search_worker = build_desktop_search_worker()
    app.state.search_worker = search_worker
    if search_worker is not None:
        search_worker.start()
    yield
    if search_worker is not None:
        await search_worker.stop()
    if scheduler is not None:
        await scheduler.stop()


app = FastAPI(
    title="Questboard API",
    version="0.2.0",
    description="AI-powered job search & application tracking API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
