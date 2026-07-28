"""Re-judge rows an ATS mislabelled remote.

Ashby's ``isRemote`` is true on every hybrid posting and never true alongside
onsite, so it means "not strictly onsite" rather than "remote". The scraper
read it before ``workplaceType`` and, worse, stamped ``remote_flag_reported``,
which ``company_classifier`` treats as definitive: a reported flag skips both
the description scan for hybrid wording and the rule that a board-reported
remote flag on a job with a street address deserves skepticism.

The classifier was not wrong, it was silenced. So this repair re-runs it with
the flag off rather than writing a second remote-detection rule. Where it now
says hybrid or onsite, the row stops claiming remote.

The re-scrape path cannot do this. It refreshes location, date_posted and
state_codes on an existing row but never is_remote, so these rows would stay
wrong through any number of future pulls.

Lives outside maintenance.py, which is already past 900 lines and holds four
repairs; a fifth belongs in its own module rather than growing that one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

REMOTE_FLAG_REPAIR_NAME = "ats_remote_flag"
REMOTE_FLAG_REPAIR_VERSION = 1

# Only Ashby ever stamped the definitive flag, so only Ashby rows were denied
# the classifier's judgment. Widen this if another scraper starts reporting.
_AFFECTED_SOURCES = ("ashby",)

_REQUIRED_COLS = ("id", "location", "description", "is_remote", "work_type", "source")


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
    from job_finder.company_classifier import classify_work_type

    clauses = " OR ".join(
        f"LOWER(COALESCE(source,'')) LIKE '%{s}%'" for s in _AFFECTED_SOURCES
    )
    rows = conn.execute(text(
        "SELECT id, location, description, work_type FROM applications "
        f"WHERE is_remote = 1 AND ({clauses}) "
        "AND LOWER(COALESCE(vertical,'career')) IN ('career', 'work')"
    )).fetchall()

    changed = 0
    for row_id, location, description, work_type in rows:
        try:
            verdict = classify_work_type(
                location or "",
                description or "",
                True,
                # The whole point: ask the classifier what it would have said
                # if the ATS had not claimed to know better.
                remote_flag_reported=False,
            )
        except Exception:
            logger.warning("remote flag repair: row %s failed, skipping", row_id,
                           exc_info=True)
            continue
        if verdict == "remote":
            continue
        # updated_at is deliberately untouched: the user's log sorts by it and
        # a data repair must not reshuffle their board.
        conn.execute(
            text("UPDATE applications SET is_remote = 0, work_type = :w WHERE id = :i"),
            {"w": verdict, "i": row_id},
        )
        changed += 1
    return changed


def repair_remote_flags(engine, *, force: bool = False) -> int:
    """Re-judge ATS rows flagged remote; returns the number corrected.

    Idempotent twice over: the version marker skips the scan on later calls,
    and a forced re-run only rewrites rows the classifier still disagrees
    with. Scan, updates and marker share one transaction, so a crash leaves
    the DB unrepaired but consistent.
    """
    inspector = inspect(engine)
    names = inspector.get_table_names()
    ready = "applications" in names and set(_REQUIRED_COLS).issubset(
        {c["name"] for c in inspector.get_columns("applications")}
    ) if "applications" in names else False

    with engine.begin() as conn:
        if (
            _applied_version(conn, REMOTE_FLAG_REPAIR_NAME)
            >= REMOTE_FLAG_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan(conn) if ready else 0
        _record_version(conn, REMOTE_FLAG_REPAIR_NAME, REMOTE_FLAG_REPAIR_VERSION)
        return changed
