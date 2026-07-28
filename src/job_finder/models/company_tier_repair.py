"""Re-judge company tiers that came from a mislabeled source board.

BuiltIn was registered as a startup board, and classify_company falls back to
the source category when no stronger signal identifies a company, so anything
arriving via BuiltIn without funding data was tiered "Early Startup". Found
live 2026-07-28: 19 rows, including CDW, a Fortune 500 IT reseller.

The category fix (builtin -> general) stops new mistiers. This repair
re-judges the stored ones: every row whose tier is Early Startup gets
reclassified with its source's CURRENT category, so a tier only survives if a
signal that still exists supports it. Rows from boards that are genuinely
startup-typed keep theirs.

Own module by the same rule as remote_flag_repair: maintenance.py already
holds four repairs and is past its size budget.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

COMPANY_TIER_REPAIR_NAME = "source_category_tier"
COMPANY_TIER_REPAIR_VERSION = 1

_REQUIRED_COLS = ("id", "company", "source", "company_type")


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
    from job_finder.company_classifier import classify_company
    from job_finder.tools.scrapers import get_registry

    categories = {
        name.lower(): getattr(meta, "category", "")
        for name, meta in get_registry().items()
    }

    rows = conn.execute(text(
        "SELECT id, company, source FROM applications "
        "WHERE company_type = 'Early Startup'"
    )).fetchall()

    changed = 0
    for row_id, company, source in rows:
        category = categories.get((source or "").lower()) or None
        try:
            verdict = classify_company(company or "", source_category=category)
        except Exception:
            logger.warning("company tier repair: row %s failed, skipping", row_id,
                           exc_info=True)
            continue
        if verdict == "Early Startup":
            continue
        # updated_at stays put: the log sorts by it and a repair must not
        # reshuffle the user's board.
        conn.execute(
            text("UPDATE applications SET company_type = :t WHERE id = :i"),
            {"t": verdict, "i": row_id},
        )
        changed += 1
    return changed


def repair_company_tiers(engine, *, force: bool = False) -> int:
    """Re-judge Early Startup tiers; returns the number corrected.

    Version-marked like the other repairs; scan, updates and marker share one
    transaction so a crash leaves the DB unrepaired but consistent.
    """
    inspector = inspect(engine)
    names = inspector.get_table_names()
    ready = "applications" in names and set(_REQUIRED_COLS).issubset(
        {c["name"] for c in inspector.get_columns("applications")}
    ) if "applications" in names else False

    with engine.begin() as conn:
        if (
            _applied_version(conn, COMPANY_TIER_REPAIR_NAME)
            >= COMPANY_TIER_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan(conn) if ready else 0
        _record_version(conn, COMPANY_TIER_REPAIR_NAME, COMPANY_TIER_REPAIR_VERSION)
        return changed
