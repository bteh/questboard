from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.config import get_settings

router = APIRouter(tags=["health"])

# Stable project root — same calculation as dependencies.py
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/worker")
def health_worker(db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.hosted_mode:
        return {"status": "disabled", "workers": []}

    from app.services import workspace_service

    workers = workspace_service.list_recent_worker_heartbeats(db)
    compatible_workers = workspace_service.list_recent_worker_heartbeats(
        db,
        expected_release=settings.resolved_app_release,
    )
    return {
        "status": "ok" if compatible_workers else "degraded",
        "release": settings.resolved_app_release,
        "compatible_workers": len(compatible_workers),
        "workers": [
            {
                "worker_id": worker.worker_id,
                "status": worker.status,
                "last_seen_at": worker.last_seen_at.isoformat(),
                "release": workspace_service.worker_heartbeat_release(worker),
                "compatible": workspace_service.worker_heartbeat_release(worker) == settings.resolved_app_release,
            }
            for worker in workers
        ],
    }


@router.get("/health/ready")
def health_ready(db: Session = Depends(get_db)):
    settings = get_settings()

    # LLM status
    llm_provider = settings.llm_provider or ""
    llm_status = "configured" if llm_provider else "not_configured"
    llm_available = False
    if llm_provider:
        try:
            from job_finder.llm_client import LLMClient
            client = LLMClient()
            llm_available = client.is_available()
        except Exception:
            pass

    # Resume detection
    resume_found = False
    resume_hint = ""
    knowledge_dir = _PROJECT_ROOT / "knowledge"
    if knowledge_dir.exists():
        pdfs = list(knowledge_dir.glob("*.pdf"))
        resume_found = len(pdfs) > 0
        if pdfs:
            resume_hint = pdfs[0].name

    # Profile detection
    profiles: list[str] = []
    try:
        config_dir = _PROJECT_ROOT / "src" / "job_finder" / "config" / "profiles"
        if config_dir.exists():
            profiles = [
                f.stem for f in config_dir.glob("*.yaml")
                if not f.stem.startswith("_")
            ]
    except Exception:
        pass

    payload = {
        "status": "ready",
        "database": "connected",
        "llm": llm_status,
        "llm_provider": llm_provider or None,
        "llm_available": llm_available,
        "resume_found": resume_found,
        "resume_file": resume_hint or None,
        "profiles": profiles,
        "setup_complete": bool(llm_provider or resume_found or profiles),
        "tips": _get_tips(llm_provider, llm_available, resume_found, profiles),
    }
    if settings.hosted_mode:
        from app.services import workspace_service

        payload["workers"] = len(workspace_service.list_recent_worker_heartbeats(db))
        payload["dev_hosted_auth"] = bool(settings.dev_hosted_auth_enabled)
        if settings.dev_hosted_auth_enabled:
            from app.services import dev_auth_service

            payload["dev_personas"] = len(dev_auth_service.list_personas())
    return payload


def _get_tips(
    llm_provider: str, llm_available: bool, resume_found: bool, profiles: list[str],
) -> list[str]:
    """Generate actionable tips for things that need setup."""
    tips = []
    if not profiles:
        tips.append("Run 'launchboard-setup' or 'make setup' to create your first profile")
    if not resume_found:
        tips.append("Add your resume PDF to the knowledge/ directory for scoring")
    if not llm_provider:
        tips.append("Set LLM_PROVIDER in .env for AI scoring (search works without it)")
    elif not llm_available:
        tips.append(f"LLM provider '{llm_provider}' is configured but not reachable")
    return tips


@router.get("/api/health/system")
def system_health(db: Session = Depends(get_db)):
    """Unified health dashboard — shows the state of every subsystem.

    Each row has: status (ok/warn/error), summary, detail, fix_action.
    The frontend renders this as a "System Health" panel with one-click
    fix buttons for anything broken.
    """
    from app.services import settings_service
    from app.services.error_translator import translate as translate_error
    from job_finder.secrets import is_available as keyring_available

    subsystems = {}

    # ── Backend ─────────────────────────────────────────────
    subsystems["backend"] = {
        "status": "ok",
        "summary": "Running",
        "detail": "API is responding on this port.",
        "fix_action": None,
    }

    # ── LLM / AI ────────────────────────────────────────────
    try:
        llm_status = settings_service.get_llm_status()
        if not llm_status.get("configured"):
            subsystems["ai"] = {
                "status": "warn",
                "summary": "Not connected",
                "detail": "AI scoring is disabled. Search works without AI but results are ranked by keyword matching only.",
                "fix_action": {"kind": "open_diagnostic", "label": "Connect AI"},
            }
        elif not llm_status.get("available"):
            err = llm_status.get("error") or {}
            subsystems["ai"] = {
                "status": "error",
                "summary": err.get("title") or "AI is not responding",
                "detail": err.get("message") or "Your AI provider is configured but not answering. Click 'Fix this' to diagnose.",
                "fix_action": err.get("next_action") or {"kind": "open_diagnostic", "label": "Diagnose"},
            }
        else:
            subsystems["ai"] = {
                "status": "ok",
                "summary": f"Connected to {llm_status.get('label') or llm_status.get('provider')}",
                "detail": f"Model: {llm_status.get('model')}",
                "fix_action": None,
            }
    except Exception as exc:
        subsystems["ai"] = {
            "status": "error",
            "summary": "Cannot check AI status",
            "detail": str(exc)[:200],
            "fix_action": {"kind": "open_diagnostic", "label": "Diagnose"},
        }

    # ── Resume ──────────────────────────────────────────────
    try:
        from app.services import workspace_service
        resume = None
        try:
            workspaces = db.query(workspace_service.Workspace).limit(1).all()
            if workspaces:
                record = workspace_service.get_workspace_resume(db, workspaces[0].id)
                if record and record.parse_status == "parsed":
                    resume = record
        except Exception:
            pass

        if resume:
            subsystems["resume"] = {
                "status": "ok",
                "summary": resume.original_filename or "Resume uploaded",
                "detail": f"Parsed successfully ({(resume.file_size or 0) // 1024} KB)",
                "fix_action": None,
            }
        else:
            subsystems["resume"] = {
                "status": "warn",
                "summary": "No resume uploaded",
                "detail": "Upload a resume to enable AI-powered scoring against your actual experience.",
                "fix_action": {"kind": "open_settings", "label": "Upload resume"},
            }
    except Exception as exc:
        subsystems["resume"] = {
            "status": "warn",
            "summary": "Resume status unknown",
            "detail": str(exc)[:200],
            "fix_action": None,
        }

    # ── Search / last run ───────────────────────────────────
    try:
        from app.services import pipeline_service
        latest = None
        for run in pipeline_service._runs.values():
            if latest is None or (run.started_at or 0) > (latest.started_at or 0):
                latest = run
        if latest is None:
            subsystems["search"] = {
                "status": "warn",
                "summary": "No searches yet",
                "detail": "Run a search from the Dashboard or Search tab.",
                "fix_action": {"kind": "open_search", "label": "New search"},
            }
        elif latest.status == "completed":
            subsystems["search"] = {
                "status": "ok",
                "summary": f"Last search completed",
                "detail": f"Run {latest.run_id[:8]} found {getattr(latest, 'jobs_found', 0)} jobs.",
                "fix_action": None,
            }
        elif latest.status == "failed":
            subsystems["search"] = {
                "status": "error",
                "summary": "Last search failed",
                "detail": getattr(latest, "error", "") or "Unknown error.",
                "fix_action": {"kind": "open_search", "label": "Retry"},
            }
        else:
            subsystems["search"] = {
                "status": "ok",
                "summary": f"Search {latest.status}",
                "detail": f"Run {latest.run_id[:8]} is {latest.status}.",
                "fix_action": None,
            }
    except Exception as exc:
        subsystems["search"] = {
            "status": "warn",
            "summary": "Search status unknown",
            "detail": str(exc)[:200],
            "fix_action": None,
        }

    # ── Key storage ─────────────────────────────────────────
    if keyring_available():
        subsystems["keychain"] = {
            "status": "ok",
            "summary": "Using OS Keychain",
            "detail": "API keys are stored securely in your system keychain.",
            "fix_action": None,
        }
    else:
        subsystems["keychain"] = {
            "status": "warn",
            "summary": "Using local file",
            "detail": "Keychain unavailable. API keys are stored in a local .env file.",
            "fix_action": None,
        }

    # Overall status: error beats warn beats ok
    overall = "ok"
    for s in subsystems.values():
        if s["status"] == "error":
            overall = "error"
            break
        if s["status"] == "warn" and overall == "ok":
            overall = "warn"

    return {"overall": overall, "subsystems": subsystems}
    # Silence unused import warning; translate_error is used indirectly via get_llm_status
    _ = translate_error
