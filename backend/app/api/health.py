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

    return {
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
