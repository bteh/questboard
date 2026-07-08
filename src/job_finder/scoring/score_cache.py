"""Per-job AI scoring disk cache.

Skips the LLM call when the same job has already been scored against the
same resume + weights. Re-discovered jobs are the dominant case — most
searches surface ~30-50% jobs we've already seen before.

The cache key fingerprints every input the scorer's output depends on:

    sha256(workspace_id + resume_text + job_url + description + weights_json)

So invalidation happens automatically when:
  - the user updates their resume → resume_text changes
  - the company edits the posting → description changes
  - the user reweights scoring dimensions → weights_json changes
  - a different workspace queries the same URL → workspace_id changes

Cache files live at ``data/cache/ai_scores/<key>.json`` and are atomically
written. A 30-day TTL guards against the (rare) case where a model upgrade
silently shifts scoring distributions; users can also blow away the dir.

Disable via ``QUESTBOARD_DISABLE_AI_SCORE_CACHE=1``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 30
CACHE_VERSION = 1

# Mirrors _ats_discovery.py — co-locate caches under data/cache.
_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "ai_scores"


def _cache_disabled() -> bool:
    return os.environ.get("QUESTBOARD_DISABLE_AI_SCORE_CACHE", "").strip().lower() in {
        "1", "true", "yes",
    }


def _cache_dir() -> Path:
    return _CACHE_DIR


def cache_key(
    workspace_id: str | None,
    resume_text: str,
    job: dict,
    scoring_config: dict | None,
) -> str:
    """Build a stable cache key for the (resume, job, weights) tuple.

    All inputs are stringified deterministically; ``scoring_config`` is
    JSON-serialized with sorted keys so dict ordering doesn't churn the key.
    """
    weights_json = json.dumps(scoring_config or {}, sort_keys=True, default=str)
    material = "|".join([
        str(workspace_id or ""),
        resume_text or "",
        str(job.get("url") or ""),
        str(job.get("description") or ""),
        weights_json,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return digest[:32]


def _path_for(key: str) -> Path:
    return _cache_dir() / f"{key}.json"


def load_cached(key: str) -> dict | None:
    """Return the cached score dict if present and fresh, else None."""
    if _cache_disabled():
        return None
    path = _path_for(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("AI score cache unreadable for %s: %s", key, exc)
        return None

    cached_at_raw = payload.get("cached_at") or ""
    try:
        cached_at = datetime.fromisoformat(cached_at_raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if datetime.now(timezone.utc) - cached_at > timedelta(days=CACHE_TTL_DAYS):
        return None

    score = payload.get("score")
    if not isinstance(score, dict):
        return None
    return score


def save_cached(key: str, score: dict) -> None:
    """Atomically persist the score dict under the given key."""
    if _cache_disabled():
        return
    if not isinstance(score, dict) or not score:
        return
    try:
        _cache_dir().mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.debug("Could not create AI score cache dir: %s", exc)
        return

    payload = {
        "version": CACHE_VERSION,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "score": score,
    }
    path = _path_for(key)
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(payload, tmp)
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except OSError as exc:
        logger.debug("Failed to persist AI score cache %s: %s", key, exc)
