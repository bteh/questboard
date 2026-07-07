"""Trust and freshness signals for a job posting.

Reddit's loudest, most-repeated grievance about job boards is ghost jobs:
stale listings, reposts that reset the visible age, and aggregators that pile
up jobs you can't apply to directly. This module turns the data we already
capture (the real post date + which source a job came from) into two honest
signals the UI can lead with:

* freshness — how old the posting actually is, by its true post date, so a
  months-old reposting can't masquerade as fresh.
* direct-from-company — whether the job came straight off a company's own
  ATS/board (Greenhouse, Lever, Ashby, Workable, Workday, a VC talent board),
  which means "apply on the real site," the thing experienced seekers trust
  over an aggregator pile.

Both are pure functions so they're trivially testable and reusable by the
serializer. Freshness is time-dependent, so callers pass ``now`` (and the UI
recomputes at display time from the raw ``date_posted`` to never go stale).
"""

from __future__ import annotations

from datetime import datetime, timezone

# Sources whose listing links straight to the employer's own board / ATS.
# Applying here means applying on the real company site — not resubmitting into
# an aggregator that may be harvesting data or listing a ghost job.
DIRECT_SOURCES: frozenset[str] = frozenset({
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "workday",
    "consider",          # a16z / VC talent-network boards (server-rendered)
    "getro",             # VC portfolio job networks
    "yc_workatastartup", # Y Combinator's Work at a Startup
})

# Age thresholds in days, by the posting's *true* post date.
FRESH_MAX_DAYS = 7     # posted within the last week
RECENT_MAX_DAYS = 30   # within the last month
AGING_MAX_DAYS = 60    # 1-2 months — starting to look stale
# > AGING_MAX_DAYS is "stale" (likely filled or a ghost job).


def is_direct_source(source: str | None) -> bool:
    """True when a job's source links straight to the company's own board."""
    if not source:
        return False
    return source.strip().lower() in DIRECT_SOURCES


def posting_age_days(
    date_posted: object,
    *,
    now: datetime | None = None,
) -> int | None:
    """Whole days since the posting's true post date, or None if unknown.

    Never returns a negative age — a future/clock-skewed date clamps to 0.
    """
    # Local import keeps this module free of scraper-package import cost.
    from job_finder.tools.scrapers._utils import _parse_posted_date

    dt = _parse_posted_date(date_posted)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    delta = now - dt
    return max(0, delta.days)


def classify_freshness(
    date_posted: object,
    date_confidence: str | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """Bucket a posting by true age: fresh | recent | aging | stale | unknown.

    Returns "unknown" when there's no verifiable date — either the source told
    us the date was a guess (``date_confidence == 'missing'``) or the value
    won't parse. We never label an unverifiable posting "fresh," because that's
    exactly the false-freshness a repost exploits.
    """
    if (date_confidence or "").strip().lower() == "missing":
        return "unknown"
    age = posting_age_days(date_posted, now=now)
    if age is None:
        return "unknown"
    if age <= FRESH_MAX_DAYS:
        return "fresh"
    if age <= RECENT_MAX_DAYS:
        return "recent"
    if age <= AGING_MAX_DAYS:
        return "aging"
    return "stale"


def is_stale(
    date_posted: object,
    date_confidence: str | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """True only when we can *prove* the posting is old (never on unknown)."""
    return classify_freshness(date_posted, date_confidence, now=now) == "stale"
