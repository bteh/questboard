"""Rewrite stored date_posted values into the one calendar shape.

board_filter_conditions implements "posted in the last N days" as a TEXT
comparison on applications.date_posted against "%Y-%m-%dT%H:%M:%S" strings.
Scrapers stored whatever the source gave them, so on 2026-09-22 the board's
7-day view hid 15 of 44 postings from that week: 1,600 rows held epoch
seconds ("1789542352", Himalayas/Getro/Lever/Arbeitnow/Ashby/Workday), 100
held RFC 2822 (We Work Remotely), and a few hundred held ISO with an offset
(Greenhouse "2026-09-15T15:07:18-04:00", read as if UTC).

normalize_posted_date is the single choke point: the write path calls it for
new rows and this repair calls it for rows already stored. Free text and
date-only values are its fixed points, so they stay byte-identical. A row
whose date_confidence is "missing" only because the old parser could not read
its date (the 100 We Work Remotely rows in RFC 2822) is re-judged once the
date parses; every other confidence value stays. The older prose repair (maintenance
.repair_dates) already converted epochs once; it is version-gated, so rows
written after it ran kept their raw shape until now.

Own module by the same rule as remote_flag_repair and company_tier_repair:
maintenance.py is past its size budget.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from job_finder.tools.scrapers._utils import date_confidence_for, normalize_posted_date

logger = logging.getLogger(__name__)

POSTED_DATE_REPAIR_NAME = "posted_date_calendar"
POSTED_DATE_REPAIR_VERSION = 1

_REQUIRED_COLS = frozenset({"id", "date_posted"})


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
    """Normalize every non-empty date_posted; returns the number rewritten."""
    rows = conn.execute(text(
        "SELECT id, date_posted, date_confidence FROM applications "
        "WHERE date_posted IS NOT NULL AND date_posted != ''"
    )).fetchall()
    changed = 0
    for row_id, date_posted, date_confidence in rows:
        try:
            normalized = normalize_posted_date(date_posted)
        except Exception:
            logger.warning("posted date repair: row %s failed, skipping", row_id,
                           exc_info=True)
            continue
        confidence = date_confidence
        if (date_confidence or "").lower() == "missing":
            confidence = date_confidence_for(normalized)
        if normalized == date_posted and confidence == date_confidence:
            continue
        # updated_at stays put: the log sorts by it and a repair must not
        # reshuffle the user's board.
        conn.execute(
            text(
                "UPDATE applications SET date_posted = :p, date_confidence = :c "
                "WHERE id = :i"
            ),
            {"p": normalized, "c": confidence, "i": row_id},
        )
        changed += 1
    return changed


def repair_posted_dates(engine, *, force: bool = False) -> int:
    """Run the calendar-shape repair once; returns rows rewritten.

    Version-marked like the other repairs; scan, updates and marker share one
    transaction so a crash leaves the DB unrepaired but consistent. A forced
    re-run rewrites nothing: the stored shape is the normalizer's fixed point.
    """
    inspector = inspect(engine)
    ready = False
    if "applications" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("applications")}
        ready = _REQUIRED_COLS <= cols

    with engine.begin() as conn:
        if (
            _applied_version(conn, POSTED_DATE_REPAIR_NAME) >= POSTED_DATE_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan(conn) if ready else 0
        _record_version(conn, POSTED_DATE_REPAIR_NAME, POSTED_DATE_REPAIR_VERSION)
        return changed
