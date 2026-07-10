"""Rotating SQLite snapshots: the local backup plan.

Every quest refresh asks for a snapshot first; one is taken when the
newest snapshot is older than the interval, so a busy day costs one copy
and a broken sweep, a bad migration, or an over-eager expiry can always
be undone by pointing at ``<data>/backups/job_tracker-<stamp>.db``.

Uses SQLite's online backup API (consistent even mid-write, WAL-safe).
Never raises: a failed backup logs loudly and the refresh proceeds; a
refresh must not die because the disk is full. Non-SQLite databases
(hosted Postgres someday) are skipped; that world gets Litestream or
managed backups instead.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_KEEP = 5
MIN_INTERVAL_HOURS = 20


def _live_sqlite_path() -> Path | None:
    """Filesystem path of the live SQLite database, or None when not SQLite."""
    from job_finder.models import database

    if database._engine is None:
        database.init_db()
    url = database._engine.url
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    return Path(url.database)


def snapshot_database(
    *,
    max_keep: int = MAX_KEEP,
    min_interval_hours: float = MIN_INTERVAL_HOURS,
) -> Path | None:
    """Take a rotating snapshot if the newest one is old enough.

    Returns the new snapshot path, or None when skipped (recent snapshot,
    non-SQLite database, or failure; failures log with the traceback).
    """
    try:
        src = _live_sqlite_path()
        if src is None or not src.exists():
            return None

        backups = src.parent / "backups"
        backups.mkdir(exist_ok=True)
        existing = sorted(backups.glob(f"{src.stem}-*.db"))

        if existing and min_interval_hours > 0:
            newest = existing[-1]
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(
                newest.stat().st_mtime, tz=timezone.utc
            )
            if age < timedelta(hours=min_interval_hours):
                return None

        # microseconds keep same-second snapshots (interval 0, tests) distinct
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        dest = backups / f"{src.stem}-{stamp}.db"

        with sqlite3.connect(src) as live, sqlite3.connect(dest) as snap:
            live.backup(snap)

        for old in sorted(backups.glob(f"{src.stem}-*.db"))[:-max_keep]:
            old.unlink(missing_ok=True)

        logger.info("database snapshot written: %s", dest)
        return dest
    except Exception:
        logger.warning("database snapshot failed (non-fatal)", exc_info=True)
        return None
