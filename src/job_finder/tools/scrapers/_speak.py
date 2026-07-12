"""Shared trust guards for the speak lane (CFP sources).

A CFP row must point at a real, non-predatory conference with a real
deadline. A live board audit (2026-07-12) confirmed the two failure
shapes this module guards:

- predatory "conference mills": pay-to-present organizers running
  generic multi-topic "summits" (a Paris "4th Tech Summit on AI &
  Robotics" on averconferences.com reached the board);
- sentinel deadlines: a placeholder far-future date (PaperCall uses
  2050-01-01) that means "no real deadline", which fails the actionable
  contract's real-date leg as surely as no deadline at all.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

# Documented pay-to-present / predatory conference organizers.
# averconferences was confirmed on the board by the audit; the rest are
# widely-documented mills of the same shape. Additions need evidence (a
# host a review confirmed predatory), never a hunch, so a real conference
# is never wrongly suppressed.
PREDATORY_CONFERENCE_HOSTS = {
    "averconferences.com",
    "waset.org",
    "omicsonline.org",
    "alliedacademies.com",
    "conferenceseries.com",
    "magnusgroup.org",
    "longdom.org",
    "pulsus.com",
    "peersalleyconferences.com",
}

# A CFP deadline this far out is a placeholder, not a real date.
_SENTINEL_YEAR = 2050


def is_predatory_host(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return any(host == d or host.endswith("." + d) for d in PREDATORY_CONFERENCE_HOSTS)


def is_sentinel_deadline(deadline: datetime) -> bool:
    """A far-future placeholder date (e.g. 2050-01-01) is not a real
    deadline; the row can't honestly claim one, so it doesn't publish."""
    return deadline.year >= _SENTINEL_YEAR
