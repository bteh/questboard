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

from job_finder.llm_client import LLMClient, FailoverLLMClient, build_llm, PRESETS
from job_finder.pipeline import JobFinderPipeline, _load_search_config
from app.config import get_settings
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


def get_llm() -> LLMClient | FailoverLLMClient:
    """Create the LLM client from the current environment.

    Reads explicitly from os.environ (which update_llm_config keeps in sync)
    and passes values directly so we don't depend on load_dotenv's file search.
    build_llm adds free failover lanes (Groq, Cerebras) automatically when a
    matching <PROVIDER>_API_KEY is set, otherwise returns a plain LLMClient.
    """
    return build_llm(
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


def get_active_workspace_context(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the hosted workspace when required, otherwise best-effort context.

    The context is IDENTITY (preferences, resume, run bookkeeping), not data
    scope. When filtering or stamping application/quest rows, pass it through
    workspace_scope_id(); never use workspace.workspace.id directly for rows.
    """
    from app.services import workspace_service

    if get_settings().hosted_mode:
        return workspace_service.require_workspace_context(db, request, validate_csrf=False)
    return workspace_service.get_workspace_context_optional(db, request)


def get_active_workspace_context_csrf(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the hosted workspace when required and validate CSRF for mutations."""
    from app.services import workspace_service

    if get_settings().hosted_mode:
        return workspace_service.require_workspace_context(db, request, validate_csrf=True)
    return workspace_service.get_workspace_context_optional(db, request)


def workspace_scope_id(workspace) -> str | None:
    """The workspace id that scopes application/quest ROWS, or None.

    Hosted mode isolates rows per visitor workspace. Local and desktop mode
    own ONE pool (workspace_id NULL): the pipeline and CLI write there, so
    scoping local reads to the anonymous session workspace hides everything
    and the board goes blank as soon as the lb_session cookie lands. The
    session workspace stays useful locally for identity only (preferences,
    resume, run history).
    """
    if workspace is not None and get_settings().hosted_mode:
        return workspace.workspace.id
    return None


def reject_legacy_route_in_hosted_mode(detail: str = "Route not available in hosted mode") -> None:
    """Block legacy single-user routes when hosted mode is enabled."""
    if get_settings().hosted_mode:
        raise HTTPException(status_code=404, detail=detail)


def require_ops_access(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """The ops surfaces (scraper health, run log, schedule) are open on
    your own machine and admin-only when hosted: run internals and error
    samples are for whoever runs the board, not for browsing."""
    settings = get_settings()
    if not settings.hosted_mode:
        return
    admins = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    if not admins:
        raise HTTPException(status_code=403, detail="Ops access is not configured")
    from app.services import workspace_service

    context = workspace_service.require_workspace_context(db, request, validate_csrf=False)
    email = (getattr(context.profile, "email", None) or "").lower()
    if email not in admins:
        raise HTTPException(status_code=403, detail="Ops access required")
