"""Re-scope stored rows whose remote region lived in the title.

Until Oct 12 2026 remote_scope was read from the location alone, so Arbeitnow's
KD Pharma "Business Intelligence Manager (m/f/d) | Remote (Europe) |
Full-time" at "Bexbach" was stored with an empty scope and the board's place
filter kept it for a Los Angeles + US-remote seeker. Save now reads the title
when the location is silent; this repair applies the same rule
(remote_scope.classify_remote_scope) to rows already stored.

Only empty scopes are touched: a scope the location stated is never
overridden by the title. The version marker is stamped only once the table
holds rows, so a fresh install does not mark the repair done before any data
arrives.

Own module by the same rule as the other repairs: maintenance.py is past its
size budget.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from job_finder.models.company_tier_repair import _applied_version, _record_version

logger = logging.getLogger(__name__)

REMOTE_SCOPE_TITLE_REPAIR_NAME = "remote_scope_from_title"
REMOTE_SCOPE_TITLE_REPAIR_VERSION = 1

_REQUIRED_COLS = frozenset({"id", "job_title", "location", "remote_scope"})


def _scan(conn) -> int:
    from job_finder.remote_scope import classify_remote_scope

    rows = conn.execute(text(
        "SELECT id, location, job_title FROM applications "
        "WHERE (remote_scope IS NULL OR remote_scope = '') "
        "AND job_title IS NOT NULL AND job_title != ''"
    )).fetchall()

    changed = 0
    for row_id, location, title in rows:
        scope = classify_remote_scope(location, title=title)
        if not scope:
            continue
        # updated_at stays untouched so the repair does not reshuffle the log.
        conn.execute(
            text("UPDATE applications SET remote_scope = :s WHERE id = :i"),
            {"s": scope, "i": row_id},
        )
        changed += 1
    return changed


def repair_remote_scope_from_titles(engine, *, force: bool = False) -> int:
    """Fill empty remote_scope from the title; returns the number of rows set."""
    inspector = inspect(engine)
    names = inspector.get_table_names()
    ready = "applications" in names and _REQUIRED_COLS.issubset(
        {c["name"] for c in inspector.get_columns("applications")}
    )

    with engine.begin() as conn:
        if (
            _applied_version(conn, REMOTE_SCOPE_TITLE_REPAIR_NAME)
            >= REMOTE_SCOPE_TITLE_REPAIR_VERSION
            and not force
        ):
            return 0
        # A fresh install runs startup repairs before its first row exists.
        # Stamping the marker then would skip rows a later import or restored
        # backup brings in, so the marker waits until there is data to judge.
        if not ready or conn.execute(text("SELECT 1 FROM applications LIMIT 1")).fetchone() is None:
            return 0
        changed = _scan(conn)
        _record_version(conn, REMOTE_SCOPE_TITLE_REPAIR_NAME, REMOTE_SCOPE_TITLE_REPAIR_VERSION)
        return changed
