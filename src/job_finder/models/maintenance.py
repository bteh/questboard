"""One-time, versioned data repairs for the local SQLite database.

Schema changes live in ``database._migrate_db``. This module is for DATA
fixes: rows written by old, buggy code that stay wrong on disk after the
code itself is fixed. Each repair records its version in the ``data_repairs``
meta table, so app startup runs it exactly once per version instead of
rescanning every launch. A failed repair rolls back without the marker and
retries on the next launch.

Current repairs:

  description_reclean v1 -- rows scraped before the _strip_html fix (audit
  2026-07-21, D1) carry markup as literal description text: entity-encoded
  Greenhouse junk, literal ``<div class="content-intro">`` tags,
  data-leveltext attribute noise. Re-cleans stored descriptions through the
  SAME cleaner the scrapers use now, so stored and fresh rows converge.
  Rows without markup remnants are left byte-identical (Ashby-style
  plaintext keeps its newlines; the cleaner would collapse them).

Runnable directly against a DB file:

    python -m job_finder.models.maintenance --db data/job_tracker.db
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import datetime, timezone
from html import unescape

from sqlalchemy import create_engine, inspect, text

from job_finder.tools.scrapers._utils import _strip_html

logger = logging.getLogger(__name__)

DESCRIPTION_REPAIR_NAME = "description_reclean"
DESCRIPTION_REPAIR_VERSION = 1

# A literal HTML tag left in stored text by the old strip-before-unescape bug.
# Requires a letter right after '<' (or '</') so prose like "a < b" never fires.
_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*>")


def _looks_dirty(description: str) -> bool:
    """True when stored text still carries markup worth re-cleaning.

    Two signals, both taken from the cleaner's own primitives: a literal
    HTML tag, or text that ``html.unescape`` would change (a real character
    reference; made-up patterns like "&Conditions;" don't count). The gate
    is deliberate: _strip_html also collapses whitespace and truncates, and
    rows from sources that never used it keep newlines on purpose. Only
    markup damage triggers a rewrite, so clean rows round-trip byte-identical.
    """
    if _TAG_RE.search(description):
        return True
    return unescape(description) != description


def _reclean(description: str) -> str:
    """Apply the scrapers' cleaner until it stops changing the text.

    Double-encoded entities can reveal new markup after one pass; looping to
    a fixed point makes the stored value stable under future re-runs. The cap
    is defensive, real content settles in one or two passes.
    """
    for _ in range(4):
        cleaned = _strip_html(description)
        if cleaned == description:
            break
        description = cleaned
    return description


def _applied_version(conn, name: str) -> int:
    """Recorded version for a repair, creating the meta table on first use."""
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
    params = {
        "n": name,
        "v": version,
        "t": datetime.now(timezone.utc).isoformat(),
    }
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


def _scan_and_repair_descriptions(conn) -> int:
    """Re-clean every dirty description; returns the number rewritten.

    Per-row failures are logged and skipped, one weird value must never
    abort the repair. ``updated_at`` is left alone on purpose: the log
    sorts by it and a data repair must not reshuffle the user's board.
    """
    rows = conn.execute(text(
        "SELECT id, description FROM applications "
        "WHERE description IS NOT NULL AND description != ''"
    )).fetchall()
    changed = 0
    for row_id, description in rows:
        if not isinstance(description, str):
            continue
        try:
            if not _looks_dirty(description):
                continue
            cleaned = _reclean(description)
        except Exception:
            logger.warning(
                "description repair: row %s failed, skipping", row_id,
                exc_info=True,
            )
            continue
        if cleaned != description:
            conn.execute(
                text("UPDATE applications SET description = :d WHERE id = :i"),
                {"d": cleaned, "i": row_id},
            )
            changed += 1
    return changed


def repair_descriptions(engine, *, force: bool = False) -> int:
    """Run the description re-clean repair once; returns rows rewritten.

    Idempotent two ways: the version marker skips the scan entirely on
    later calls (pass ``force=True`` to scan anyway), and a forced re-run
    rewrites only rows the cleaner still changes. Scan, updates, and the
    marker share one transaction, so a crash leaves the DB unrepaired but
    consistent and the repair retries next launch.
    """
    has_applications = "applications" in inspect(engine).get_table_names()
    with engine.begin() as conn:
        if (
            _applied_version(conn, DESCRIPTION_REPAIR_NAME)
            >= DESCRIPTION_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan_and_repair_descriptions(conn) if has_applications else 0
        _record_version(
            conn, DESCRIPTION_REPAIR_NAME, DESCRIPTION_REPAIR_VERSION
        )
        return changed


def run_startup_repairs(engine) -> None:
    """Startup hook, called from ``database._migrate_db``. Never raises."""
    try:
        changed = repair_descriptions(engine)
        if changed:
            logger.info(
                "description repair v%d: re-cleaned %d row(s)",
                DESCRIPTION_REPAIR_VERSION, changed,
            )
    except Exception:
        logger.warning(
            "description repair failed; will retry next launch", exc_info=True
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-clean stored job descriptions damaged by the pre-2026-07-21 "
            "HTML cleaner. Safe to re-run; a version marker makes later runs "
            "no-ops."
        ),
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to job_tracker.db (default: the app's data dir)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Scan even if the version marker says this repair already ran",
    )
    args = parser.parse_args(argv)

    from job_finder.models.database import DB_PATH

    db_path = args.db or DB_PATH
    if not os.path.exists(db_path):
        parser.error(f"database file not found: {db_path}")

    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    try:
        changed = repair_descriptions(engine, force=args.force)
    finally:
        engine.dispose()
    print(
        f"description repair v{DESCRIPTION_REPAIR_VERSION}: "
        f"{changed} row(s) re-cleaned in {db_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
