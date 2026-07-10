"""Healthy-run-gated expiry: listings leave the board only with evidence.

The trust contract (docs/source-reliability.md): a broken scraper must
never empty the board, and the board must never keep showing offers the
source itself stopped listing. Both sides are served by two rules, each
declared per source in its own registry entry:

- **Absence** (``full_snapshot=True`` sources): one fetch is the source's
  entire current set, so a row missing from TWO consecutive healthy runs
  is provably gone. One healthy absence is never enough (a fetch can
  glitch), and unhealthy runs prove nothing.
- **Staleness** (``stale_after_days`` sources): windowed fetches
  (newest-N) cannot prove absence, so rows expire when the source has not
  confirmed them for the declared number of days. If the scraper breaks,
  rows age out at the TTL and the health endpoint has been shouting the
  whole time; showing month-old "live" offers would be the bigger lie.

Backstops, because expiry is where trust dies fastest:

- **Mass-expiry guard**: a sweep refusing to expire more than 30% of a
  source's live rows (past a floor of 10) skips entirely and reports
  why. A site changing its URL format makes every row "absent" at once;
  that must page a human, not wipe a lane.
- **Tombstones, not deletes**: expired rows keep their record and their
  place in the user's log (the log filters by status, never url_status);
  they only leave the board.
- **Revival**: a source re-listing an expired URL flips it back on the
  next save (save_application stamps last_seen_at and clears the
  tombstone).

Career rows are exempt: the career pipeline has its own lifecycle
(filters purge, check_urls verifies). This module only ever touches the
source it is asked about, which is always a quest source in practice.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# a sweep may not silently expire more than this share of a source's live
# rows (once past the absolute floor); breaching it reports and skips
GUARD_FRACTION = 0.30
GUARD_FLOOR = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _previous_healthy_run_started(session, source: str):
    """Start time of the healthy run BEFORE the latest healthy one, or None.

    Healthy means the fetch finished and found rows. Two healthy runs of
    history are required before absence proves anything.
    """
    from job_finder.models.database import ScrapeRunRecord

    runs = (
        session.query(ScrapeRunRecord.started_at)
        .filter(
            ScrapeRunRecord.source == source,
            ScrapeRunRecord.finish_reason == "ok",
            ScrapeRunRecord.rows_found > 0,
        )
        .order_by(ScrapeRunRecord.started_at.desc())
        .limit(2)
        .all()
    )
    if len(runs) < 2:
        return None
    return runs[1][0]


def expire_for_source(source: str, *, now: datetime | None = None) -> dict:
    """Apply the source's declared expiry rules. Returns a summary dict.

    Summary keys: ``expired`` (rows tombstoned), ``rule`` (absence,
    stale, or none), ``skipped`` (guard or precondition reason, when the
    sweep did not run).
    """
    from job_finder.models.database import ApplicationRecord, get_session
    from job_finder.tools.scrapers._registry import get_registry

    meta = get_registry().get(source)
    if meta is None or meta.vertical == "career":
        return {"expired": 0, "rule": "none", "skipped": "not an expirable source"}
    if not meta.full_snapshot and not meta.stale_after_days:
        return {"expired": 0, "rule": "none", "skipped": "no expiry contract declared"}

    now = now or _utcnow()
    session = get_session()
    try:
        live_filter = (
            (ApplicationRecord.source == source)
            & (ApplicationRecord.vertical != "career")
            & (ApplicationRecord.url_status.notin_(("dead", "expired")))
        )
        live_count = session.query(ApplicationRecord).filter(live_filter).count()
        if live_count == 0:
            return {"expired": 0, "rule": "none", "skipped": "no live rows"}

        if meta.full_snapshot:
            rule = "absence"
            prev_started = _previous_healthy_run_started(session, source)
            if prev_started is None:
                return {"expired": 0, "rule": rule, "skipped": "needs two healthy runs of history"}
            cutoff = prev_started
        else:
            rule = "stale"
            cutoff = now - timedelta(days=int(meta.stale_after_days or 0))

        candidates = (
            session.query(ApplicationRecord)
            .filter(live_filter)
            .filter(ApplicationRecord.last_seen_at.isnot(None))
            .filter(ApplicationRecord.last_seen_at < cutoff)
            .all()
        )
        if not candidates:
            return {"expired": 0, "rule": rule}

        if len(candidates) > GUARD_FLOOR and len(candidates) > GUARD_FRACTION * live_count:
            logger.warning(
                "expiry guard tripped for %s: %d of %d live rows would expire; skipping sweep",
                source, len(candidates), live_count,
            )
            return {
                "expired": 0,
                "rule": rule,
                "skipped": f"mass-expiry guard: {len(candidates)} of {live_count} live rows",
            }

        for row in candidates:
            row.url_status = "expired"
            # updated_at stays put: tombstoning must never reshuffle the log
        session.commit()
        logger.info("expired %d %s rows (%s rule)", len(candidates), source, rule)
        return {"expired": len(candidates), "rule": rule}
    except Exception:
        session.rollback()
        logger.warning("expiry sweep for %s failed (non-fatal)", source, exc_info=True)
        return {"expired": 0, "rule": "none", "skipped": "sweep error"}
    finally:
        session.close()
