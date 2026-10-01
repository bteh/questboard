"""Freshness evidence for a stored posting. Pure, clock injected.

A posting is fresh when any of these holds, in this order of evidence:
``posted`` (the source post date is within the window), ``updated`` (the
source says it edited the posting within the window), ``listed`` (a pull
within the window still saw it on the board), ``verified_open`` (the link
check said alive within the window). Real cases (Oct 1 2026): Natera, Airbnb
and Stripe lead and manager postings, posted in spring and edited in late
September, were hidden by the posted window alone.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

FRESHNESS_BASES: tuple[str, ...] = ("posted", "updated", "listed", "verified_open")


def _anchor_age_days(
    anchor: datetime | str | None, *, now: datetime | None = None
) -> float | None:
    """Age of an anchor timestamp in days, or None when it can't be read.

    Accepts the ORM's datetime (naive means UTC, how SQLite hands
    ``date_found`` back) or a stored ISO string.
    """
    if isinstance(anchor, str):
        try:
            anchor = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(anchor, datetime):
        return None
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    elapsed = now - anchor.astimezone(timezone.utc)
    return max(0.0, elapsed.total_seconds() / 86_400)


def _relative_offset_days(lowered: str) -> float | None:
    if re.fullmatch(r"(?:re)?posted\s+today|today", lowered):
        return 0.0
    if re.fullmatch(r"(?:re)?posted\s+yesterday|yesterday", lowered):
        return 1.0
    relative = re.fullmatch(
        r"(?:(?:re)?posted\s+)?(\d+)\s+"
        r"(minute|minutes|hour|hours|day|days)\s+ago",
        lowered,
    )
    if not relative:
        return None
    amount = int(relative.group(1))
    unit = relative.group(2)
    if unit.startswith("minute"):
        return amount / (24 * 60)
    if unit.startswith("hour"):
        return amount / 24
    return float(amount)


def _source_age_days(
    value: str | None,
    anchor: datetime | str | None = None,
    *,
    now: datetime | None = None,
) -> float | None:
    """Normalize exact and human-readable source dates into an age in days.

    Relative prose ("Reposted 3 Days Ago", "Yesterday") only means something
    relative to the moment the source said it, which is when WE scraped the
    row. ``anchor`` is that moment (the record's date_found): with it, age =
    age(anchor) + the stated offset, so a row scraped six days ago saying
    "3 Days Ago" reads ~9 days old instead of eternally 3. Without an anchor
    the prose is unknowable and returns None. Absolute values (ISO, epoch)
    carry their own instant and ignore the anchor.
    """

    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    now = now or datetime.now(timezone.utc)
    offset_days = _relative_offset_days(normalized.lower())
    if offset_days is not None:
        anchor_age = _anchor_age_days(anchor, now=now)
        if anchor_age is None:
            return None
        return anchor_age + offset_days

    # Only the two real epoch widths: 10 digits is seconds, 13 is
    # milliseconds. An 11 or 12 digit value is malformed; guessing its unit
    # lands it far in the future and clamps to age 0 (reads as posted today),
    # so leave it unknown instead.
    if re.fullmatch(r"\d{10}|\d{13}", normalized):
        timestamp = int(normalized)
        if len(normalized) == 13:
            timestamp /= 1000
        try:
            posted = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return max(0.0, (now - posted).total_seconds() / 86_400)

    return _anchor_age_days(normalized, now=now)


def _within(age_days: float | None, window_days: int) -> bool:
    return age_days is not None and age_days <= window_days


def freshness_basis(row: Any, window_days: int, now: datetime | None = None) -> str | None:
    """Name the strongest evidence that ``row`` is still fresh, or None.

    None means one of two things the caller tells apart by the source date:
    a row with an unknown post date has no basis and keeps today's
    unknown-date path; a row with a known post date older than the window and
    no other evidence is provably stale.
    """
    now = now or datetime.now(timezone.utc)
    posted_at = getattr(row, "date_posted", None)
    found_at = getattr(row, "date_found", None)
    if _source_age_days(posted_at, found_at, now=now) is None:
        return None
    if _within(_source_age_days(posted_at, found_at, now=now), window_days):
        return "posted"
    updated_at = getattr(row, "date_updated", None)
    if _within(_source_age_days(updated_at, found_at, now=now), window_days):
        return "updated"
    if _within(_anchor_age_days(getattr(row, "last_seen_at", None), now=now), window_days):
        return "listed"
    if (getattr(row, "url_status", None) or "") == "alive" and _within(
        _anchor_age_days(getattr(row, "last_checked_at", None), now=now), window_days
    ):
        return "verified_open"
    return None
