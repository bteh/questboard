"""Curated Qwick LA on-ramp (odd kind): pick up hospitality shifts.

Qwick fills one-off restaurant, bar, and event shifts (server, barback,
dishwasher, line cook, event help) with independent pros. Its Los Angeles
market page lists the shift types but no open shifts without an account,
so this is one static row linking there. The search function makes no
network calls.

HONESTY: pay is set per shift by the business, so none is stated.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_POSTER = {
    "title": "Pick up restaurant and event shifts in LA on Qwick",
    "company": "Qwick",
    "url": "https://www.qwick.com/market/california/los-angeles/",
    "description": (
        "Qwick posts one-off hospitality shifts around Los Angeles: serving, "
        "barbacking, dish, prep, and event help. Make a pro profile and claim "
        "the shifts you want."
    ),
    "bring": "a Qwick pro profile",
    "catch": "pay is set per shift by the business",
}


@register_scraper(
    name="qwick_onramp",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated link to Qwick's LA hospitality shift market",
    category="odd",
    kind="odd",
    full_snapshot=True,
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=("qwick.com",),
)
def search_qwick_onramp(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated Qwick LA card. ``roles`` is ignored."""
    if max_results <= 0:
        return []
    row = {
        "title": _POSTER["title"],
        "company": _POSTER["company"],
        "location": "Los Angeles, CA",
        "url": _POSTER["url"],
        "source": "qwick_onramp",
        "vertical": "odd",
        "description": _POSTER["description"],
        "salary_min": None,
        "salary_max": None,
        "date_posted": "",
        "is_rolling": True,
        "first_quest_ok": False,
        "quest": {"bring": _POSTER["bring"], "catch": _POSTER["catch"]},
    }
    logger.info("qwick_onramp: 1 curated on-ramp")
    return [row]
