"""Tag stored rows from YC companies' job boards as startups.

Real case, Oct 12 2026: TRM Labs, Hightouch and Deepgram sat on Brian's Find
Work board as company_type "Unknown", so the "Startups & founding" chip never
showed them. New saves read the board through fill_funding_from_text; this
applies the same lookup to rows already stored.

The marker version is the snapshot's build date, so shipping a rebuilt
config/startup_boards.json re-runs the pass once for the boards it added.
Only empty funding stages are filled and only Unknown or startup tiers are
re-judged: a stated round or a stronger tier is never overwritten.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from job_finder.models.company_tier_repair import _applied_version, _record_version

logger = logging.getLogger(__name__)

STARTUP_BOARD_REPAIR_NAME = "startup_boards"

_REQUIRED_COLS = frozenset({"id", "company", "job_url", "company_type", "funding_stage"})
_RETIERABLE = frozenset({"", "unknown", "early startup", "growth stage"})
# Board hosts only; the URL test happens in Python against the snapshot.
_SELECT = (
    "SELECT id, company, job_url, company_type, total_funding FROM applications "
    "WHERE (funding_stage IS NULL OR funding_stage = ''){career_only} AND ("
    "job_url LIKE '%ashbyhq.com/%' OR job_url LIKE '%greenhouse.io/%' "
    "OR job_url LIKE '%lever.co/%')"
)


def repair_startup_boards(engine) -> int:
    """Stamp YC stages onto stored rows; returns rows changed."""
    from job_finder.company_classifier import classify_company, known_list_tier
    from job_finder.startup_boards import snapshot_version, startup_stage_for_url

    version = snapshot_version()
    if not version:
        return 0
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return 0
    cols = frozenset(c["name"] for c in inspector.get_columns("applications"))
    if not _REQUIRED_COLS <= cols:
        return 0
    has_funding = "total_funding" in cols
    select = _SELECT.format(career_only=" AND vertical = 'career'" if "vertical" in cols else "")
    if not has_funding:
        select = select.replace("company_type, total_funding", "company_type, NULL")

    changed = 0
    with engine.begin() as conn:
        if _applied_version(conn, STARTUP_BOARD_REPAIR_NAME) >= version:
            return 0
        for row_id, company, job_url, company_type, total_funding in conn.execute(
            text(select)
        ).fetchall():
            current = (company_type or "").strip()
            if current.lower() not in _RETIERABLE or known_list_tier(company or ""):
                continue
            stage = startup_stage_for_url(job_url)
            if not stage:
                continue
            verdict = classify_company(
                company or "", funding_stage=stage, total_funding=total_funding,
            )
            # updated_at stays put: the log sorts by it.
            conn.execute(
                text(
                    "UPDATE applications SET funding_stage = :stage, "
                    "company_type = :tier WHERE id = :id"
                ),
                {"stage": stage, "tier": verdict, "id": row_id},
            )
            changed += 1
        _record_version(conn, STARTUP_BOARD_REPAIR_NAME, version)
    return changed
