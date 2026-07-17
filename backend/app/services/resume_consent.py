"""Local, human-granted consent to expose the resume to the connected agent.

The resume is sensitive PII. The MCP tool read_resume_for_matching returns it
only when a PERSON has granted consent. Consent lives in a small file next to
the local database (DATA_DIR/resume_consent.json). Nothing in the MCP surface
can write it: a human grants it from the Questboard app (or the
scripts/resume_consent.py CLI), never the model. Consent may carry a TTL and
can be revoked.

The store is keyed by workspace_id so a shared machine's separate profiles keep
separate consent.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FILENAME = "resume_consent.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _data_dir() -> Path:
    from app.config import get_settings

    base = getattr(get_settings(), "data_dir", "") or os.getenv("DATA_DIR") or "."
    return Path(base)


def _path() -> Path:
    return _data_dir() / _FILENAME


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def grant(workspace_id: str, *, ttl_hours: int | None = None) -> dict[str, Any]:
    """Record human consent to expose this workspace's resume. TTL optional."""
    now = _now()
    entry = {
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat()
        if ttl_hours is not None
        else None,
    }
    data = _load()
    data[workspace_id] = entry
    _save(data)
    logger.info("Resume consent granted for workspace %s (ttl_hours=%s)", workspace_id, ttl_hours)
    return entry


def revoke(workspace_id: str) -> None:
    data = _load()
    if workspace_id in data:
        del data[workspace_id]
        _save(data)
        logger.info("Resume consent revoked for workspace %s", workspace_id)


def is_granted(workspace_id: str) -> bool:
    entry = _load().get(workspace_id)
    if not isinstance(entry, dict) or not entry.get("granted_at"):
        return False
    expires_at = entry.get("expires_at")
    if expires_at:
        try:
            if _now() >= datetime.fromisoformat(expires_at):
                return False
        except ValueError:
            return False
    return True


def status(workspace_id: str) -> dict[str, Any]:
    entry = _load().get(workspace_id) or {}
    return {
        "granted": is_granted(workspace_id),
        "granted_at": entry.get("granted_at"),
        "expires_at": entry.get("expires_at"),
    }
