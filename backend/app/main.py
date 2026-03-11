import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.dependencies import _src_dir  # noqa: F401 — ensures src/ is on sys.path
from app.api.router import api_router
from app.models.database import init_db
from app.services.scheduler_service import start_scheduler, stop_scheduler

_DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]


def _get_cors_origins() -> list[str]:
    """Read CORS origins from CORS_ORIGINS env var (comma-separated) or use defaults."""
    raw = os.environ.get("CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return _DEFAULT_CORS_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Launchboard API",
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
