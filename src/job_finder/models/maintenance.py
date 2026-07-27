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

  cross_source_dedup v1 -- rows saved before the squashed-company dedup fix
  can sit on the board twice: the same opening once from a direct ATS source
  and once from an aggregator, under different URLs (the Alo "Manager of
  Data Engineering" pair: "Aloyoga" on greenhouse vs "ALO" on LinkedIn).
  Finds those clusters with the shared key in job_finder.dedup, keeps the
  best row (protected statuses first, then direct source, then richness),
  merges pay/dates the keeper lacked, and tombstones the losers with
  status='expired' plus a note. Losers are never hard-deleted, so the log
  and its receipts survive.

  date_reclean v1 -- rows scraped before the freshness-anchor fix store the
  source's words ("Reposted 3 Days Ago", "Yesterday") or a bare unix epoch
  as date_posted. Relative prose anchored to NOW at query time made those
  rows eternally fresh: a row scraped six days ago saying "3 Days Ago" read
  as 3 days old forever. The repair converts prose to ISO computed as
  date_found (scrape time) minus the stated offset with date_confidence
  'fuzzy', converts bare 10-13 digit epochs to the ISO instant they encode
  (confidence kept), and leaves rows with no usable date_found untouched.

  salary_backfill v1 -- career rows saved before the parser learned single
  stated figures ("$130,000/year", "the base salary range ... is $180,000")
  and the 'USD'/'US$' ISO forms show "reward not stated" though the pay sits
  in the description. The repair re-runs the same extractor a fresh pull uses
  over rows with no pay at all, fills salary_min/max (+ currency, period,
  annualized) with salary_source='parsed_from_description', and never
  overwrites a value the scraper already reported.

Runnable directly against a DB file:

    python -m job_finder.models.maintenance --db data/job_tracker.db
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import unescape

from sqlalchemy import create_engine, inspect, text

from job_finder.dedup import cluster_jobs, is_protected_status, richness_key
from job_finder.tools.scrapers._utils import (
    _annualized_or_none,
    _strip_html,
    extract_salary_range,
)

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


DUPLICATE_REPAIR_NAME = "cross_source_dedup"
DUPLICATE_REPAIR_VERSION = 1

# Columns the duplicate repair reads and writes. All of them exist after
# _migrate_db has run (the startup path); the guard in repair_duplicates
# skips the scan on a legacy DB reached through the CLI before migration.
_DUP_REQUIRED_COLS = (
    "id", "job_title", "company", "location", "job_url", "source", "status",
    "description", "vertical", "notes", "url_status",
)
_DUP_OPTIONAL_COLS = (
    "is_remote", "profile", "workspace_id",
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "salary_min_annualized", "salary_max_annualized", "salary_source",
    "date_posted", "date_confidence",
)
_DUP_PAY_COLS = (
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "salary_min_annualized", "salary_max_annualized", "salary_source",
)


def _keeper_rank(job: dict) -> tuple:
    """Sort key for the cluster keeper (bigger wins).

    A protected status (anything past found/reviewed records user work)
    always wins its cluster regardless of source. Among equals, a live row
    beats a url_status tombstone, then the shared richness order applies
    (direct ATS source, stated pay, description length).
    """
    row = job["_row"]
    protected = 1 if is_protected_status(row.get("status")) else 0
    live = 0 if (row.get("url_status") or "").lower() in ("dead", "expired") else 1
    return (protected, live) + richness_key(job)


def _merge_missing_fields(conn, keeper: dict, losers: list[dict]) -> None:
    """Copy pay/date/description data the keeper lacks from its losers.

    Losers are consulted best-first. ``updated_at`` is left alone on purpose,
    a data repair must not reshuffle the user's board.
    """
    row = keeper["_row"]
    updates: dict[str, object] = {}
    ordered = sorted(losers, key=_keeper_rank, reverse=True)

    for col in _DUP_PAY_COLS:
        if col not in row or row.get(col):
            continue
        for loser in ordered:
            value = loser["_row"].get(col)
            if value:
                updates[col] = value
                break

    if "date_posted" in row and (row.get("date_confidence") or "").lower() not in (
        "exact", "fuzzy",
    ):
        for loser in ordered:
            lrow = loser["_row"]
            if lrow.get("date_posted") and (
                (lrow.get("date_confidence") or "").lower() in ("exact", "fuzzy")
            ):
                updates["date_posted"] = lrow["date_posted"]
                updates["date_confidence"] = lrow.get("date_confidence") or ""
                break

    if not (row.get("description") or "").strip():
        best_desc = max(
            (loser["_row"].get("description") or "" for loser in ordered),
            key=len,
            default="",
        )
        if best_desc:
            updates["description"] = best_desc

    if updates:
        assignments = ", ".join(f"{col} = :{col}" for col in updates)
        updates["_id"] = row["id"]
        conn.execute(
            text(f"UPDATE applications SET {assignments} WHERE id = :_id"),
            updates,
        )


def _collapse_cluster(conn, cluster: list[dict]) -> int:
    """Collapse one duplicate cluster; returns the number of losers expired.

    Rows whose status records user work (clipped, applied, ...) are never
    losers: they all survive, and the best of them becomes the keeper the
    found/reviewed copies merge into.
    """
    keeper = max(cluster, key=_keeper_rank)
    losers = [
        job for job in cluster
        if job is not keeper and not is_protected_status(job["_row"].get("status"))
    ]
    if not losers:
        return 0

    _merge_missing_fields(conn, keeper, losers)

    keeper_row = keeper["_row"]
    for job in losers:
        row = job["_row"]
        note = (
            f"Cross-source duplicate of #{keeper_row['id']} "
            f"({keeper.get('source') or 'unknown source'}, "
            f"{keeper.get('url') or 'no url'}). This {job.get('source') or 'duplicate'} "
            f"copy was collapsed by data repair {DUPLICATE_REPAIR_NAME} "
            f"v{DUPLICATE_REPAIR_VERSION}."
        )
        prior = (row.get("notes") or "").strip()
        conn.execute(
            text(
                "UPDATE applications SET status = 'expired', "
                "url_status = 'expired', notes = :n WHERE id = :i"
            ),
            {"n": f"{prior}\n{note}" if prior else note, "i": row["id"]},
        )
        logger.info(
            "duplicate repair: expired #%s (%s, %s) into #%s (%s, %s) for '%s / %s'",
            row["id"], job.get("source"), job.get("url") or "no url",
            keeper_row["id"], keeper.get("source"), keeper.get("url") or "no url",
            keeper.get("company"), keeper.get("title"),
        )
    return len(losers)


def _scan_and_collapse_duplicates(conn, available_cols: set[str]) -> int:
    """Collapse every cross-source duplicate cluster; returns losers expired.

    Career rows only (two quests from the same org with the same title are
    usually different sessions), scoped by (workspace_id, profile) so rows
    from different boards never merge into each other. Per-cluster failures
    are logged and skipped, one weird cluster must never abort the repair.
    """
    select_cols = list(_DUP_REQUIRED_COLS) + [
        c for c in _DUP_OPTIONAL_COLS if c in available_cols
    ]
    rows = conn.execute(text(
        f"SELECT {', '.join(select_cols)} FROM applications "
        "WHERE vertical = 'career' "
        "AND (status IS NULL OR lower(status) != 'expired')"
    )).mappings().fetchall()

    scopes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        row = dict(r)
        scopes[(row.get("workspace_id") or "", row.get("profile") or "")].append({
            "title": row.get("job_title") or "",
            "company": row.get("company") or "",
            "location": row.get("location") or "",
            "is_remote": bool(row.get("is_remote")),
            "url": row.get("job_url") or "",
            "source": row.get("source") or "",
            "description": row.get("description") or "",
            "salary_min": row.get("salary_min"),
            "salary_max": row.get("salary_max"),
            "_row": row,
        })

    changed = 0
    for jobs in scopes.values():
        clusters, _keyless = cluster_jobs(jobs)
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            try:
                changed += _collapse_cluster(conn, cluster)
            except Exception:
                logger.warning(
                    "duplicate repair: cluster for %r / %r failed, skipping",
                    cluster[0].get("company"), cluster[0].get("title"),
                    exc_info=True,
                )
    return changed


def repair_duplicates(engine, *, force: bool = False) -> int:
    """Run the cross-source duplicate collapse once; returns losers expired.

    Same idempotency contract as repair_descriptions: the version marker
    skips the scan entirely on later calls (``force=True`` scans anyway),
    and a forced re-run finds nothing new because losers leave the scan's
    status filter. Scan, updates, and the marker share one transaction, so
    a crash leaves the DB unrepaired but consistent, and the repair retries
    next launch.
    """
    inspector = inspect(engine)
    has_applications = "applications" in inspector.get_table_names()
    available: set[str] = set()
    if has_applications:
        available = {c["name"] for c in inspector.get_columns("applications")}
    runnable = has_applications and set(_DUP_REQUIRED_COLS).issubset(available)
    with engine.begin() as conn:
        if (
            _applied_version(conn, DUPLICATE_REPAIR_NAME)
            >= DUPLICATE_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan_and_collapse_duplicates(conn, available) if runnable else 0
        _record_version(conn, DUPLICATE_REPAIR_NAME, DUPLICATE_REPAIR_VERSION)
        return changed


DATE_REPAIR_NAME = "date_reclean"
DATE_REPAIR_VERSION = 1

# Columns the date repair reads and writes; all exist after _migrate_db.
_DATE_REQUIRED_COLS = ("id", "date_posted", "date_confidence", "date_found")

# The relative-prose grammar the board's freshness parser understands
# (local_agent_service._source_age_days). Kept in exact parity: whatever
# that parser calls prose, this repair converts; everything else it leaves.
_PROSE_TODAY_RE = re.compile(r"(?:re)?posted\s+today|today")
_PROSE_YESTERDAY_RE = re.compile(r"(?:re)?posted\s+yesterday|yesterday")
_PROSE_RELATIVE_RE = re.compile(
    r"(?:(?:re)?posted\s+)?(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago"
)
_EPOCH_RE = re.compile(r"\d{10,13}")


def _prose_offset(value: str) -> timedelta | None:
    """The backward offset a relative-prose date states, else None."""
    lowered = " ".join(value.strip().split()).lower()
    if _PROSE_TODAY_RE.fullmatch(lowered):
        return timedelta()
    if _PROSE_YESTERDAY_RE.fullmatch(lowered):
        return timedelta(days=1)
    relative = _PROSE_RELATIVE_RE.fullmatch(lowered)
    if not relative:
        return None
    amount = int(relative.group(1))
    unit = relative.group(2)
    if unit.startswith("minute"):
        return timedelta(minutes=amount)
    if unit.startswith("hour"):
        return timedelta(hours=amount)
    return timedelta(days=amount)


def _parse_anchor(value) -> datetime | None:
    """date_found as a UTC datetime, however the driver hands it back."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reclean_date(date_posted: str, date_found) -> tuple[str, str | None] | None:
    """(new date_posted, new confidence or None to keep) for one row.

    None means leave the row byte-identical: already ISO, free text outside
    the prose grammar, or prose with no usable date_found anchor. The output
    is naive-UTC ISO at second precision, the shape every reader handles
    (string comparison in SQL, fromisoformat in the services).
    """
    normalized = " ".join(str(date_posted or "").strip().split())
    if not normalized:
        return None

    offset = _prose_offset(normalized)
    if offset is not None:
        anchor = _parse_anchor(date_found)
        if anchor is None:
            return None
        posted = anchor - offset
        return posted.strftime("%Y-%m-%dT%H:%M:%S"), "fuzzy"

    if _EPOCH_RE.fullmatch(normalized):
        timestamp = int(normalized)
        if len(normalized) == 13:
            timestamp /= 1000
        try:
            posted = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return posted.strftime("%Y-%m-%dT%H:%M:%S"), None

    return None


def _scan_and_repair_dates(conn, available_cols: set[str]) -> int:
    """Convert every prose/epoch date_posted; returns the number rewritten.

    Per-row failures are logged and skipped, one weird value must never
    abort the repair. ``updated_at`` is left alone on purpose: the log
    sorts by it and a data repair must not reshuffle the user's board.
    """
    if not set(_DATE_REQUIRED_COLS).issubset(available_cols):
        return 0
    rows = conn.execute(text(
        "SELECT id, date_posted, date_confidence, date_found FROM applications "
        "WHERE date_posted IS NOT NULL AND date_posted != ''"
    )).fetchall()
    changed = 0
    for row_id, date_posted, date_confidence, date_found in rows:
        if not isinstance(date_posted, str):
            continue
        try:
            result = _reclean_date(date_posted, date_found)
        except Exception:
            logger.warning(
                "date repair: row %s failed, skipping", row_id, exc_info=True
            )
            continue
        if result is None:
            continue
        new_posted, new_confidence = result
        if new_confidence is None:
            conn.execute(
                text("UPDATE applications SET date_posted = :p WHERE id = :i"),
                {"p": new_posted, "i": row_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE applications SET date_posted = :p, "
                    "date_confidence = :c WHERE id = :i"
                ),
                {"p": new_posted, "c": new_confidence, "i": row_id},
            )
        changed += 1
    return changed


def repair_dates(engine, *, force: bool = False) -> int:
    """Run the date re-clean repair once; returns rows rewritten.

    Same idempotency contract as repair_descriptions: the version marker
    skips the scan entirely on later calls (``force=True`` scans anyway),
    and a forced re-run converts nothing because ISO output no longer
    matches the prose or epoch shapes. Scan, updates, and the marker share
    one transaction, so a crash leaves the DB unrepaired but consistent and
    the repair retries next launch.
    """
    inspector = inspect(engine)
    has_applications = "applications" in inspector.get_table_names()
    available: set[str] = set()
    if has_applications:
        available = {c["name"] for c in inspector.get_columns("applications")}
    with engine.begin() as conn:
        if (
            _applied_version(conn, DATE_REPAIR_NAME) >= DATE_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan_and_repair_dates(conn, available) if has_applications else 0
        _record_version(conn, DATE_REPAIR_NAME, DATE_REPAIR_VERSION)
        return changed


SALARY_REPAIR_NAME = "salary_backfill"
SALARY_REPAIR_VERSION = 1

# Columns the salary repair writes. All exist after _migrate_db; the guard in
# repair_salaries skips the scan on a legacy DB reached before migration.
_SALARY_WRITE_COLS = (
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "salary_min_annualized", "salary_max_annualized", "salary_source",
)


def _scan_and_repair_salaries(conn) -> int:
    """Backfill pay for career rows the improved parser can now read.

    Only rows with no pay at all are touched (both salary_min and salary_max
    null), so a value the scraper already reported is never overwritten. The
    parser is the same one finalize_scraper_jobs runs, so backfilled rows match
    what a fresh pull would store. Per-row failures are logged and skipped, one
    weird description must never abort the repair.
    """
    rows = conn.execute(text(
        "SELECT id, description FROM applications "
        "WHERE (vertical IS NULL OR vertical = 'career') "
        "AND salary_min IS NULL AND salary_max IS NULL "
        "AND description IS NOT NULL AND description != ''"
    )).fetchall()
    changed = 0
    for row_id, description in rows:
        if not isinstance(description, str):
            continue
        try:
            found = extract_salary_range(description)
            if found.salary_min is None and found.salary_max is None:
                continue
            conn.execute(
                text(
                    "UPDATE applications SET "
                    "salary_min = :mn, salary_max = :mx, "
                    "salary_currency = :cur, salary_period = :per, "
                    "salary_min_annualized = :mna, salary_max_annualized = :mxa, "
                    "salary_source = 'parsed_from_description' WHERE id = :i"
                ),
                {
                    "mn": found.salary_min,
                    "mx": found.salary_max,
                    "cur": found.currency or "",
                    "per": found.period or "",
                    "mna": _annualized_or_none(found.salary_min, found.period),
                    "mxa": _annualized_or_none(found.salary_max, found.period),
                    "i": row_id,
                },
            )
            changed += 1
        except Exception:
            logger.warning(
                "salary repair: row %s failed, skipping", row_id, exc_info=True,
            )
    return changed


def repair_salaries(engine, *, force: bool = False) -> int:
    """Run the salary backfill repair once; returns rows filled.

    Same idempotency contract as the other repairs: the version marker skips
    the scan on later calls (``force=True`` scans anyway), and a forced re-run
    fills nothing new because parsed rows no longer match the both-null filter.
    Scan, updates, and the marker share one transaction. Guarded on the salary
    columns so a pre-migration DB reached through the CLI is a no-op.
    """
    inspector = inspect(engine)
    has_applications = "applications" in inspector.get_table_names()
    has_cols = False
    if has_applications:
        cols = {c["name"] for c in inspector.get_columns("applications")}
        has_cols = set(_SALARY_WRITE_COLS).issubset(cols)
    with engine.begin() as conn:
        if (
            _applied_version(conn, SALARY_REPAIR_NAME) >= SALARY_REPAIR_VERSION
            and not force
        ):
            return 0
        changed = _scan_and_repair_salaries(conn) if has_cols else 0
        _record_version(conn, SALARY_REPAIR_NAME, SALARY_REPAIR_VERSION)
        return changed


DESCRIPTION_REFETCH_LIMIT = 50

# Only sources whose detail page we know how to read. A source missing from
# here is left alone rather than guessed at.
_REFETCH_SOURCES = ("linkedin", "builtin")


# What we store per row. The parser reads the FULL page first: LinkedIn puts
# the hiring range last, after the duties, so a cap applied before extraction
# silently decides which jobs have pay. The real Disney row stored 3,000
# characters of responsibilities and not one dollar figure that way.
DESCRIPTION_STORE_CHARS = 3000


def _fetch_linkedin_description(url: str) -> str:
    """The job body from a LinkedIn posting page, or "" if it isn't there.

    Returns the WHOLE body. Truncation is the caller's, after parsing."""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
        timeout=10,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    element = (
        soup.select_one(".description__text")
        or soup.select_one(".show-more-less-html__markup")
        or soup.select_one("[class*='description']")
    )
    return element.get_text(separator="\n", strip=True) if element else ""


def _fetch_description(source: str, url: str) -> str:
    """One place that knows how to recover a missing body, per source."""
    name = (source or "").strip().lower()
    if name == "linkedin":
        return _fetch_linkedin_description(url)
    if name == "builtin":
        from job_finder.tools.scrapers.builtin import fetch_builtin_detail

        return str((fetch_builtin_detail(url) or {}).get("description") or "")
    return ""


def refetch_missing_descriptions(engine, *, limit: int = DESCRIPTION_REFETCH_LIMIT) -> int:
    """Refetch bodies for stored rows saved without one; returns rows filled.

    The pull's own backfill only sees jobs in the current run, and a row
    already on the board is deduped away long before it gets there. So a row
    saved empty stays empty forever: 35 of 53 LinkedIn rows and 18 of 28
    BuiltIn rows were, and one of them was the Disney posting that read
    "REWARD not stated" while its page stated $171,600-$252,000.

    Deliberately NOT part of ``run_startup_repairs``. Every other repair here
    is pure SQL; this one makes network calls, and launching the app must never
    depend on LinkedIn answering. Run it from the CLI, bounded by ``limit``.

    A row is only ever improved. A fetch that comes back empty writes nothing,
    and pay the scraper reported is never replaced by pay parsed from prose.
    """
    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return 0
    cols = {c["name"] for c in inspector.get_columns("applications")}
    if not {"description", "job_url", "source"}.issubset(cols):
        return 0
    can_write_pay = set(_SALARY_WRITE_COLS).issubset(cols)

    placeholders = ", ".join(f":s{i}" for i in range(len(_REFETCH_SOURCES)))
    params: dict = {f"s{i}": name for i, name in enumerate(_REFETCH_SOURCES)}
    params["lim"] = max(0, int(limit))
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, source, job_url, salary_min, salary_max FROM applications "
            "WHERE (vertical IS NULL OR vertical IN ('career', 'work')) "
            "AND (description IS NULL OR description = '') "
            "AND job_url IS NOT NULL AND job_url != '' "
            f"AND LOWER(source) IN ({placeholders}) "
            "AND (url_status IS NULL OR url_status NOT IN ('dead', 'expired')) "
            "ORDER BY id DESC LIMIT :lim"
        ), params).fetchall()

    filled = 0
    for row_id, source, url, salary_min, salary_max in rows:
        try:
            description = _fetch_description(source, url)
        except Exception:
            logger.warning(
                "description refetch: row %s failed, skipping", row_id, exc_info=True,
            )
            continue
        if not description:
            continue
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE applications SET description = :d WHERE id = :i"),
                {"d": description[:DESCRIPTION_STORE_CHARS], "i": row_id},
            )
            # Parse the full page, not the stored excerpt. Reported pay still
            # wins over anything read out of prose.
            if can_write_pay and salary_min is None and salary_max is None:
                found = extract_salary_range(description)
                if found.salary_min is not None or found.salary_max is not None:
                    conn.execute(
                        text(
                            "UPDATE applications SET "
                            "salary_min = :mn, salary_max = :mx, "
                            "salary_currency = :cur, salary_period = :per, "
                            "salary_min_annualized = :mna, "
                            "salary_max_annualized = :mxa, "
                            "salary_source = 'parsed_from_description' "
                            "WHERE id = :i"
                        ),
                        {
                            "mn": found.salary_min,
                            "mx": found.salary_max,
                            "cur": found.currency or "",
                            "per": found.period or "",
                            "mna": _annualized_or_none(found.salary_min, found.period),
                            "mxa": _annualized_or_none(found.salary_max, found.period),
                            "i": row_id,
                        },
                    )
        filled += 1
    return filled


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
    try:
        collapsed = repair_duplicates(engine)
        if collapsed:
            logger.info(
                "duplicate repair v%d: expired %d duplicate row(s)",
                DUPLICATE_REPAIR_VERSION, collapsed,
            )
    except Exception:
        logger.warning(
            "duplicate repair failed; will retry next launch", exc_info=True
        )
    try:
        converted = repair_dates(engine)
        if converted:
            logger.info(
                "date repair v%d: converted %d date_posted row(s)",
                DATE_REPAIR_VERSION, converted,
            )
    except Exception:
        logger.warning(
            "date repair failed; will retry next launch", exc_info=True
        )
    try:
        filled = repair_salaries(engine)
        if filled:
            logger.info(
                "salary repair v%d: backfilled %d row(s)",
                SALARY_REPAIR_VERSION, filled,
            )
    except Exception:
        logger.warning(
            "salary repair failed; will retry next launch", exc_info=True
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the one-time data repairs (description re-clean, cross-source "
            "duplicate collapse, date re-clean, salary backfill) against a "
            "local DB. Safe to re-run; version markers make later runs no-ops."
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
        help="Scan even if the version markers say these repairs already ran",
    )
    parser.add_argument(
        "--refetch-descriptions",
        nargs="?",
        type=int,
        const=DESCRIPTION_REFETCH_LIMIT,
        default=0,
        metavar="N",
        help=(
            "Also refetch up to N stored rows saved with no description "
            f"(default {DESCRIPTION_REFETCH_LIMIT}). Off unless asked for: "
            "unlike the other repairs this one makes network calls."
        ),
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
        collapsed = repair_duplicates(engine, force=args.force)
        converted = repair_dates(engine, force=args.force)
        filled = repair_salaries(engine, force=args.force)
        refetched = (
            refetch_missing_descriptions(engine, limit=args.refetch_descriptions)
            if args.refetch_descriptions
            else 0
        )
    finally:
        engine.dispose()
    print(
        f"description repair v{DESCRIPTION_REPAIR_VERSION}: "
        f"{changed} row(s) re-cleaned in {db_path}"
    )
    print(
        f"duplicate repair v{DUPLICATE_REPAIR_VERSION}: "
        f"{collapsed} duplicate row(s) expired in {db_path}"
    )
    print(
        f"date repair v{DATE_REPAIR_VERSION}: "
        f"{converted} date_posted row(s) converted in {db_path}"
    )
    print(
        f"salary repair v{SALARY_REPAIR_VERSION}: "
        f"{filled} row(s) backfilled in {db_path}"
    )
    if args.refetch_descriptions:
        print(
            f"description refetch: {refetched} row(s) filled from their "
            f"posting page in {db_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
