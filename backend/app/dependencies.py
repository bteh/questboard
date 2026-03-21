"""Shared FastAPI dependency injection helpers."""

from __future__ import annotations

import re
import sys
import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

# Ensure src/ is importable when running from backend/
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Resolve the project-root .env so load_dotenv always finds it,
# regardless of which directory the process was started from.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")

# Load .env once at import time
load_dotenv(_ENV_PATH, override=False)

from job_finder.llm_client import LLMClient, PRESETS
from job_finder.pipeline import JobFinderPipeline, _load_search_config
from app.models.database import get_db

_PROFILE_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def sanitize_profile(name: str) -> str:
    """Validate and return a safe profile name.

    Only alphanumeric characters, hyphens, and underscores are allowed.
    Raises HTTPException(400) if the name contains path separators,
    dot-dot sequences, or any other disallowed characters.
    """
    if not name or not _PROFILE_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Invalid profile name: only alphanumeric characters, hyphens, and underscores are allowed",
        )
    return name


def get_llm() -> LLMClient:
    """Create an LLMClient from current environment.

    Reads explicitly from os.environ (which update_llm_config keeps in sync)
    and passes values directly so we don't depend on load_dotenv's file search.
    """
    return LLMClient(
        provider=os.getenv("LLM_PROVIDER") or None,
        base_url=os.getenv("LLM_BASE_URL") or None,
        api_key=os.getenv("LLM_API_KEY") or None,
        model=os.getenv("LLM_MODEL") or None,
    )


def get_pipeline(profile: str | None = None) -> JobFinderPipeline:
    """Create a pipeline instance for the given profile."""
    llm = get_llm()
    return JobFinderPipeline(llm=llm if llm.is_configured else None, profile=profile)


def get_config(profile: str | None = None) -> dict:
    """Load search config for a profile."""
    return _load_search_config(profile)


def get_workspace_context(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the active hosted workspace/session context."""
    from app.services import workspace_service

    return workspace_service.require_workspace_context(db, request, validate_csrf=False)


def get_workspace_context_csrf(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the active hosted workspace/session context and validate CSRF."""
    from app.services import workspace_service

    return workspace_service.require_workspace_context(db, request, validate_csrf=True)
