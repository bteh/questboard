"""Reset the alive stamps the link checker gave to closed-job pages.

Until Oct 6 2026 the checker trusted an HTTP 200 on hosts that keep a closed
job's URL alive and render a notice instead (BuiltIn, LinkedIn, Workable,
Greenhouse, Lever, Getro boards). Those rows carry url_status "alive", and
since 0.2.13 that stamp keeps a row on the board past the freshness window
(freshness basis "verified_open"). Found live on Brian's board: 6 of 8
BuiltIn rows stamped alive were dead, 4 of 8 LinkedIn, 4 Workable, and 153 of
471 rows were on the board only because of the stamp.

The detector fix (job_finder.closed_pages) stops new stamps. This repair
resets the stored ones on template hosts to "unknown" with no
last_checked_at, so the scheduler's rolling re-verification, which takes
never-checked rows first, re-proves each with the new detector. Rows on hosts
without a template keep their stamp: nothing changed about how those were
judged.

Version 2 (Nov 5 2026): the checker also trusted a 200 after a redirect to a
listing index (15 of 15 stale Himalayas rows landed on himalayas.app/jobs, 5
of 10 Greenhouse rows on a careers index; see closed_pages.dead_redirect).
Those stamps sit on any host, so v2 resets alive rows whose board presence
rests on the stamp alone: a source date (posted, and updated if present)
older than STALE_DAYS and no listing pull within STALE_DAYS. Rows with any
other freshness evidence keep their stamp. A database already at v1 gets only
the v2 pass.

Own module by the same rule as the other repairs: maintenance.py is past its
size budget.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text

from job_finder.closed_pages import template_for

logger = logging.getLogger(__name__)

LINK_STATUS_REPAIR_NAME = "soft_closed_links"
LINK_STATUS_REPAIR_VERSION = 2
STALE_DAYS = 45

_REQUIRED_COLS = frozenset({"id", "job_url", "url_status", "last_checked_at"})


def _applied_version(conn, name: str) -> int:
    conn.execute(text(
        "CREATE TABLE IF NOT EXISTS data_repairs ("
        "name VARCHAR(64) PRIMARY KEY, "
        "version INTEGER NOT NULL, "
        "applied_at VARCHAR(40) DEFAULT '')"
    ))
    row = conn.execute(
        text("SELECT version FROM data_repairs WHERE name = :n"), {"n": name}
    ).fetchone()
    return int(row[0]) if row else 0


def _record_version(conn, name: str, version: int) -> None:
    params = {"n": name, "v": version, "t": datetime.now(timezone.utc).isoformat()}
    updated = conn.execute(
        text("UPDATE data_repairs SET version = :v, applied_at = :t WHERE name = :n"),
        params,
    )
    if updated.rowcount == 0:
        conn.execute(
            text(
                "INSERT INTO data_repairs (name, version, applied_at) "
                "VALUES (:n, :v, :t)"
            ),
            params,
        )


def _instant(value) -> datetime | None:
    """An absolute timestamp, or None. Relative prose ("3 days ago") and
    unreadable values return None, so such rows keep their stamp."""
    if isinstance(value, datetime):
        moment = value
    else:
        raw = str(value or "").strip()
        if re.fullmatch(r"\d{10}|\d{13}", raw):
            seconds = int(raw) / (1000 if len(raw) == 13 else 1)
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _rests_on_stamp(row, cutoff: datetime) -> bool:
    posted = _instant(row.get("date_posted"))
    if posted is None or posted > cutoff:
        return False
    if row.get("date_updated"):
        updated = _instant(row["date_updated"])
        if updated is None or updated > cutoff:
            return False
    seen = row.get("last_seen_at")
    if seen:
        seen_at = _instant(seen)
        if seen_at is None or seen_at > cutoff:
            return False
    return True


def _reset(conn, ids: list[int]) -> None:
    if ids:
        # updated_at stays put: the log sorts by it and a repair must not
        # reshuffle the user's board.
        conn.execute(
            text(
                "UPDATE applications SET url_status = 'unknown', "
                "last_checked_at = NULL WHERE id = :i"
            ),
            [{"i": row_id} for row_id in ids],
        )


def _scan(conn, applied: int, columns: frozenset[str], now: datetime) -> int:
    ids: set[int] = set()
    if applied < 1:
        rows = conn.execute(text(
            "SELECT id, job_url FROM applications "
            "WHERE url_status = 'alive' AND job_url IS NOT NULL"
        )).fetchall()
        ids.update(row_id for row_id, url in rows if template_for(str(url or "")) is not None)
    if applied < 2 and "date_posted" in columns:
        optional = [c for c in ("date_updated", "last_seen_at") if c in columns]
        select = ", ".join(["id", "date_posted", *optional])
        rows = conn.execute(text(
            f"SELECT {select} FROM applications "
            "WHERE url_status = 'alive' AND job_url IS NOT NULL"
        )).mappings().all()
        cutoff = now - timedelta(days=STALE_DAYS)
        ids.update(row["id"] for row in rows if _rests_on_stamp(row, cutoff))
    _reset(conn, sorted(ids))
    return len(ids)


def _application_columns(engine) -> frozenset[str]:
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return frozenset()
    return frozenset(c["name"] for c in inspector.get_columns("applications"))


def repair_link_status(
    engine, *, force: bool = False, now: datetime | None = None
) -> int:
    """Run the reset once; returns the number of rows sent back for re-check.

    Scan, updates and the version marker share one transaction, so a crash
    leaves the DB unrepaired but consistent and the repair retries next
    launch.
    """
    columns = _application_columns(engine)
    ready = _REQUIRED_COLS <= columns
    with engine.begin() as conn:
        applied = _applied_version(conn, LINK_STATUS_REPAIR_NAME)
        if applied >= LINK_STATUS_REPAIR_VERSION:
            if not force:
                return 0
            applied = 0
        now = now or datetime.now(timezone.utc)
        changed = _scan(conn, applied, columns, now) if ready else 0
        _record_version(conn, LINK_STATUS_REPAIR_NAME, LINK_STATUS_REPAIR_VERSION)
        return changed
