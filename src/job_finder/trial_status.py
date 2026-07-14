"""Recruiting-status re-verification for ClinicalTrials.gov rows.

A closed trial is invisible to the dead-link pass: ctgov study pages
answer HTTP 200 forever, so a row can sit on the board months after
recruiting ended. The registry's own v2 API is the only honest signal.
This module re-asks it in batches (``filter.ids``) and tombstones rows
whose overallStatus is no longer RECRUITING, using the same mechanism
as expiry.py (url_status="expired"; the row keeps its record and its
place in the log, it only leaves the board).

Decisions pinned here:

- ENROLLING_BY_INVITATION counts as closed. The study is active, but
  only pre-selected participants may join, so a board visitor cannot
  act on it.
- A failed or ambiguous check never expires a row. Network errors and
  ids missing from a healthy response land in ``errors`` and the row
  stays untouched, first in line for the next batch.
- A confirmed RECRUITING row gets last_seen_at refreshed: the registry
  vouching for the study is the same evidence a re-listing gives, and
  it keeps the staleness TTL from expiring rows the source itself
  still stands behind.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from job_finder.tools.scrapers._utils import _get_json

logger = logging.getLogger(__name__)

_API_URL = "https://clinicaltrials.gov/api/v2/studies"
_FIELDS = ",".join((
    "protocolSection.identificationModule.nctId",
    "protocolSection.statusModule.overallStatus",
))
_CHUNK_SIZE = 100
_MAX_PAGES = 5
_NCT_RE = re.compile(r"NCT\d+", re.IGNORECASE)

# The only status a newcomer can act on (see module docstring for why
# ENROLLING_BY_INVITATION is out).
_OPEN_STATUSES = frozenset({"RECRUITING"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fetch_statuses(nct_ids: list[str]) -> dict[str, str]:
    """{nctId: overallStatus} for one id chunk; missing ids stay absent.

    The response is unordered (verified live 2026-07-14), so statuses map
    by nctId, never by position. nextPageToken is followed defensively
    even though pageSize == len(chunk) should keep everything on one page.
    """
    statuses: dict[str, str] = {}
    params = {
        "filter.ids": ",".join(nct_ids),
        "fields": _FIELDS,
        "pageSize": str(len(nct_ids)),
    }
    page_token: str | None = None
    for _ in range(_MAX_PAGES):
        page_params = dict(params)
        if page_token:
            page_params["pageToken"] = page_token
        data = _get_json(_API_URL, params=page_params)
        if not isinstance(data, dict):
            break
        studies = data.get("studies")
        if isinstance(studies, list):
            for study in studies:
                ps = study.get("protocolSection") if isinstance(study, dict) else None
                if not isinstance(ps, dict):
                    continue
                nct = (ps.get("identificationModule") or {}).get("nctId")
                status = (ps.get("statusModule") or {}).get("overallStatus")
                if nct and status:
                    statuses[str(nct).upper()] = str(status)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return statuses


def reverify_trials(
    db_session_or_path: Session | str | None = None,
    max_checks: int = 200,
) -> dict:
    """Re-check recruiting status for visible clinicaltrials rows.

    Accepts an open SQLAlchemy session (the caller keeps ownership and
    closes it), a database path (re-inits the process engine, test use),
    or None for the process default session.

    Returns counts: ``checked`` rows examined, ``expired`` tombstoned,
    ``kept`` confirmed recruiting, ``errors`` rows the check could not
    settle (always kept).
    """
    from job_finder.models.database import ApplicationRecord, get_session, init_db

    owns_session = not isinstance(db_session_or_path, Session)
    if isinstance(db_session_or_path, Session):
        session = db_session_or_path
    else:
        if db_session_or_path is not None:
            init_db(str(db_session_or_path))
        session = get_session()

    checked = expired = kept = errors = 0
    try:
        rows = (
            session.query(ApplicationRecord)
            .filter(
                ApplicationRecord.source == "clinicaltrials",
                ApplicationRecord.url_status.notin_(("dead", "expired")),
                ApplicationRecord.job_url.isnot(None),
            )
            .order_by(ApplicationRecord.last_checked_at.asc().nullsfirst())
            .limit(max(0, int(max_checks)))
            .all()
        )
        checked = len(rows)
        if not rows:
            return {"checked": 0, "expired": 0, "kept": 0, "errors": 0}

        parsed: list[tuple] = []
        for row in rows:
            m = _NCT_RE.search(row.job_url or "")
            parsed.append((row, m[0].upper() if m else None))

        unique_ids = list(dict.fromkeys(nct for _, nct in parsed if nct))
        statuses: dict[str, str] = {}
        for i in range(0, len(unique_ids), _CHUNK_SIZE):
            statuses.update(_fetch_statuses(unique_ids[i : i + _CHUNK_SIZE]))

        now = _utcnow()
        for row, nct in parsed:
            if nct is None:
                # no NCT id can ever settle; stamp it so the rolling
                # batch moves past instead of re-picking it forever
                logger.warning(
                    "clinicaltrials row %s has no NCT id in %r", row.id, row.job_url
                )
                row.last_checked_at = now
                errors += 1
                continue
            status = statuses.get(nct)
            if status is None:
                errors += 1
                continue
            row.last_checked_at = now
            if status in _OPEN_STATUSES:
                row.url_status = "alive"
                row.last_seen_at = now
                kept += 1
            else:
                row.url_status = "expired"
                expired += 1
        session.commit()
        logger.info(
            "trial re-verify: %d checked, %d kept recruiting, %d expired, %d unsettled",
            checked, kept, expired, errors,
        )
        return {"checked": checked, "expired": expired, "kept": kept, "errors": errors}
    except Exception:
        session.rollback()
        logger.warning("trial re-verification failed (non-fatal)", exc_info=True)
        return {"checked": checked, "expired": 0, "kept": 0, "errors": errors + 1}
    finally:
        if owns_session:
            session.close()
