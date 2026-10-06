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

Own module by the same rule as the other repairs: maintenance.py is past its
size budget.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from job_finder.closed_pages import template_for

logger = logging.getLogger(__name__)

LINK_STATUS_REPAIR_NAME = "soft_closed_links"
LINK_STATUS_REPAIR_VERSION = 1

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


def _scan(conn) -> int:
    rows = conn.execute(text(
        "SELECT id, job_url FROM applications "
        "WHERE url_status = 'alive' AND job_url IS NOT NULL"
    )).fetchall()
    stale = [
        {"i": row_id} for row_id, url in rows if template_for(str(url or "")) is not None
    ]
    if stale:
        # updated_at stays put: the log sorts by it and a repair must not
        # reshuffle the user's board.
        conn.execute(
            text(
                "UPDATE applications SET url_status = 'unknown', "
                "last_checked_at = NULL WHERE id = :i"
            ),
            stale,
        )
    return len(stale)


def _application_columns(engine) -> frozenset[str]:
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return frozenset()
    return frozenset(c["name"] for c in inspector.get_columns("applications"))


def repair_link_status(engine, *, force: bool = False) -> int:
    """Run the reset once; returns the number of rows sent back for re-check.

    Scan, updates and the version marker share one transaction, so a crash
    leaves the DB unrepaired but consistent and the repair retries next
    launch.
    """
    ready = _REQUIRED_COLS <= _application_columns(engine)
    with engine.begin() as conn:
        if _applied_version(conn, LINK_STATUS_REPAIR_NAME) >= LINK_STATUS_REPAIR_VERSION:
            if not force:
                return 0
        changed = _scan(conn) if ready else 0
        _record_version(conn, LINK_STATUS_REPAIR_NAME, LINK_STATUS_REPAIR_VERSION)
        return changed
