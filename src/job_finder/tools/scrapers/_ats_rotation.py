"""Per-pull cursor for the cold lane of the verified ATS catalogs.

The cold slice used to be keyed to the UTC calendar day. That only covers
the whole catalog for someone who pulls every single day. A user who pulls
twice a week only ever sees the slices of the days he pulls, and the boards
in the other slices are never scanned (Oct 1 2026: 11 pull days since Sep 16
had reached 49% of the Greenhouse catalog and 43% of Workable). Keying the
slice to a cursor that moves once per pull makes N pulls, on any dates, cover
N slices.

The cursor lives in ``<cache dir>/ats_rotation_<host>.json`` beside the
discovery cache. A call within ``REPEAT_WINDOW`` of the last advance returns
the same slice again, so a second call inside one run (or a retried pull)
does not burn a slice. A missing or corrupt file starts over at 0.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CURSOR_VERSION = 1
REPEAT_WINDOW = timedelta(hours=2)
_LOCK = threading.Lock()


def cursor_path(cache_dir: Path, host: str) -> Path:
    return cache_dir / f"ats_rotation_{host}.json"


def _read_state(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cursor = int(payload["cursor"])
        size = int(payload.get("size") or 0)
        advanced_at = datetime.fromisoformat(str(payload["advanced_at"]))
        slugs = [str(s) for s in (payload.get("slugs") or [])]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    if advanced_at.tzinfo is None:
        advanced_at = advanced_at.replace(tzinfo=timezone.utc)
    return {"cursor": cursor, "size": size, "advanced_at": advanced_at, "slugs": slugs}


def _write_state(
    path: Path, host: str, cursor: int, slugs: list[str], advanced_at: datetime,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CURSOR_VERSION,
        "host": host,
        "cursor": cursor,
        "size": len(slugs),
        "advanced_at": advanced_at.isoformat(),
        "slugs": slugs,
    }
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp",
    ) as tmp:
        json.dump(payload, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _wrapped_slice(slugs: list[str], start: int, size: int) -> list[str]:
    end = start + size
    if end <= len(slugs):
        return slugs[start:end]
    return slugs[start:] + slugs[: end - len(slugs)]


def next_slice(
    host: str,
    slugs: list[str],
    *,
    batch_size: int,
    now: datetime,
    cache_dir: Path,
) -> set[str]:
    """Return this pull's slice of ``slugs`` and move the cursor past it."""
    size = min(int(batch_size), len(slugs))
    if size <= 0:
        return set()
    path = cursor_path(cache_dir, host)
    with _LOCK:
        state = _read_state(path)
        if state is not None:
            elapsed = now - state["advanced_at"]
            if timedelta(0) <= elapsed < REPEAT_WINDOW:
                repeat = state["slugs"] or _wrapped_slice(
                    slugs, state["cursor"] % len(slugs), size,
                )
                return set(repeat)
            start = (state["cursor"] + (state["size"] or size)) % len(slugs)
        else:
            start = 0
        chosen = _wrapped_slice(slugs, start, size)
        try:
            _write_state(path, host, start, chosen, now)
        except OSError as exc:
            logger.warning("ATS rotation cursor for %s not saved: %s", host, exc)
        return set(chosen)
