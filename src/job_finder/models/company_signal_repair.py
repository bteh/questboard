"""Fill funding and crypto signals from stored posting text, once.

Real case, Oct 1 2026: 391 of 464 rows on Brian's Find Work board carried
company_type "Unknown" and empty industry_tags, so the "Startups & founding"
chip showed 5 companies and the "Crypto" chip missed TRM Labs and Alpaca.
Scrapers never fill funding_stage or total_funding, yet 15 of those postings
state their round in the description. company_signals reads the text at save
time from now on; this repair applies the same reading to rows already
stored, under its own versioned marker.

Rows tiered by a stronger signal (FAANG+, Big Tech, Enterprise, Midsize)
keep their tier and their empty funding fields: "Series B" in a bank's
posting is about its customers, and the startup shelf trusts funding_stage
on its own. Only Unknown and startup tiers are re-judged.

Own module by the same rule as company_tier_repair: maintenance.py is past
its size budget.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from job_finder.models.company_tier_repair import _applied_version, _record_version

logger = logging.getLogger(__name__)

COMPANY_SIGNAL_REPAIR_NAME = "company_signals"
COMPANY_SIGNAL_REPAIR_VERSION = 1

# Descriptions run to 3,000 characters and the table holds ~18,000 rows;
# a keyset-paged scan keeps memory flat inside the one transaction.
BATCH_SIZE = 500

_REQUIRED_COLS = frozenset({
    "id", "company", "company_type", "funding_stage", "total_funding",
    "industry_tags", "description",
})
_RETIERABLE = frozenset({"", "unknown", "early startup", "growth stage", "elite startup"})
# Side quests are not employers: a casting call for a "Dating Series" is not
# a Series A. Career rows only, like the taxonomy repair.
_SELECT_BATCH = (
    "SELECT id, company, company_type, funding_stage, total_funding, "
    "industry_tags, description FROM applications "
    "WHERE id > :after{career_only} AND (company_type IS NULL OR company_type = 'Unknown' "
    "OR industry_tags IS NULL OR industry_tags IN ('', '[]')) "
    "ORDER BY id LIMIT :limit"
)


def _row_updates(
    company: str | None,
    company_type: str | None,
    funding_stage: str | None,
    total_funding: str | None,
    industry_tags: str | None,
    description: str | None,
) -> dict[str, str]:
    from job_finder.company_classifier import classify_company
    from job_finder.company_signals import funding_signals, industry_signals
    from job_finder.company_taxonomy import is_known_crypto_company, parse_tags, tags_json

    updates: dict[str, str] = {}
    current = (company_type or "").strip()
    if current.lower() in _RETIERABLE:
        found = funding_signals(description or "")
        stage = funding_stage or found.get("funding_stage")
        amount = total_funding or found.get("total_funding")
        if stage and not funding_stage:
            updates["funding_stage"] = stage
        if amount and not total_funding:
            updates["total_funding"] = amount
        if stage or amount:
            verdict = classify_company(
                company or "", funding_stage=stage, total_funding=amount
            )
            if verdict not in ("Unknown", current):
                updates["company_type"] = verdict

    tags = parse_tags(industry_tags)
    if "crypto" not in tags and (
        "crypto" in industry_signals(company or "", description or "")
        or is_known_crypto_company(company)
    ):
        updates["industry_tags"] = tags_json([*tags, "crypto"])
    return updates


def _scan(conn, *, has_vertical: bool) -> int:
    select = text(_SELECT_BATCH.format(
        career_only=" AND vertical = 'career'" if has_vertical else ""
    ))
    changed = 0
    after = 0
    while True:
        rows = conn.execute(select, {"after": after, "limit": BATCH_SIZE}).fetchall()
        if not rows:
            return changed
        for row_id, *fields in rows:
            after = row_id
            try:
                updates = _row_updates(*fields)
            except Exception:
                logger.warning(
                    "company signal repair: row %s failed, skipping", row_id,
                    exc_info=True,
                )
                continue
            if not updates:
                continue
            # updated_at stays put: the log sorts by it and a repair must not
            # reshuffle the user's board.
            assignments = ", ".join(f"{col} = :{col}" for col in updates)
            conn.execute(
                text(f"UPDATE applications SET {assignments} WHERE id = :id"),
                {**updates, "id": row_id},
            )
            changed += 1


def _application_columns(engine) -> frozenset[str]:
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return frozenset()
    return frozenset(c["name"] for c in inspector.get_columns("applications"))


def repair_company_signals(engine, *, force: bool = False) -> int:
    """Read funding and crypto signals into stored rows; returns rows changed.

    Scan, updates and the version marker share one transaction so a crash
    leaves the DB unrepaired but consistent. A second run is a no-op.
    """
    cols = _application_columns(engine)
    ready = _REQUIRED_COLS <= cols
    with engine.begin() as conn:
        if (
            _applied_version(conn, COMPANY_SIGNAL_REPAIR_NAME) >= COMPANY_SIGNAL_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan(conn, has_vertical="vertical" in cols) if ready else 0
        _record_version(conn, COMPANY_SIGNAL_REPAIR_NAME, COMPANY_SIGNAL_REPAIR_VERSION)
        return changed
