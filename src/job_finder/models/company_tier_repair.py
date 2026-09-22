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

Second pass, 2026-09-22: ELITE_STARTUPS hardcoded Airbnb (public since Dec
2020), Figma (public since July 2025) and eight decades-old quant firms, and
the known-list check outranks every other signal, so 21 Airbnb rows sat on the
"Startups & founding" shelf as Elite Startup. The list fix stops new stamps;
this pass re-stamps stored rows for exactly those ten companies. It carries
its own marker so the first pass is never re-run: that one re-judges Early
Startup rows without their funding signals, which is lossy for rows saved
since it ran.

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

PUBLIC_COMPANY_TIER_REPAIR_NAME = "public_company_tier"
PUBLIC_COMPANY_TIER_REPAIR_VERSION = 1

# Normalized names that left ELITE_STARTUPS on 2026-09-22. Only these rows are
# re-stamped; every other Elite Startup row keeps whatever signal tiered it.
FORMER_ELITE_STARTUPS: frozenset[str] = frozenset({
    "airbnb", "figma",
    "citadel", "jane street", "hudson river trading", "two sigma",
    "de shaw", "jump trading", "tower research", "virtu financial",
})

_REQUIRED_COLS = frozenset({"id", "company", "source", "company_type"})
_PUBLIC_REQUIRED_COLS = frozenset({
    "id", "company", "company_type", "funding_stage", "total_funding",
})


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


def _rejudge_former_elite_startups(conn) -> int:
    from job_finder.company_classifier import _normalize_company_name, classify_company

    rows = conn.execute(text(
        "SELECT id, company, company_type, funding_stage, total_funding "
        "FROM applications"
    )).fetchall()

    changed = 0
    for row_id, company, current, funding_stage, total_funding in rows:
        if _normalize_company_name(company or "") not in FORMER_ELITE_STARTUPS:
            continue
        verdict = classify_company(
            company or "", funding_stage=funding_stage, total_funding=total_funding
        )
        if verdict == current:
            continue
        conn.execute(
            text("UPDATE applications SET company_type = :t WHERE id = :i"),
            {"t": verdict, "i": row_id},
        )
        changed += 1
    return changed


def _run_pass(conn, name: str, version: int, scan, *, ready: bool, force: bool) -> int:
    if _applied_version(conn, name) >= version and not force:
        return 0
    changed = scan(conn) if ready else 0
    _record_version(conn, name, version)
    return changed


def _application_columns(engine) -> frozenset[str]:
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return frozenset()
    return frozenset(c["name"] for c in inspector.get_columns("applications"))


def repair_company_tiers(engine, *, force: bool = False) -> int:
    """Run both tier repairs; returns the number of rows corrected.

    Each pass is version-marked on its own so a pass already applied is never
    re-run. Scan, updates and markers share one transaction so a crash leaves
    the DB unrepaired but consistent.
    """
    cols = _application_columns(engine)

    with engine.begin() as conn:
        changed = _run_pass(
            conn, COMPANY_TIER_REPAIR_NAME, COMPANY_TIER_REPAIR_VERSION, _scan,
            ready=_REQUIRED_COLS <= cols, force=force,
        )
        changed += _run_pass(
            conn, PUBLIC_COMPANY_TIER_REPAIR_NAME, PUBLIC_COMPANY_TIER_REPAIR_VERSION,
            _rejudge_former_elite_startups,
            ready=_PUBLIC_REQUIRED_COLS <= cols, force=force,
        )
        return changed
