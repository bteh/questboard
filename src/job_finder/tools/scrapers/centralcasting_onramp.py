"""Curated Central Casting LA on-ramp (perform kind): background work.

Central Casting books background actors for LA film and TV. Its job
board at blog.centralcasting.com/jobs-la/ sits behind a robots.txt that
disallows every crawler, so nothing here fetches it: this is one static
row linking there. The search function makes no network calls.

HONESTY: day rates vary by booking and union status, so no pay is
stated.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_POSTER = {
    "title": "Background acting work in LA through Central Casting",
    "company": "Central Casting",
    "url": "https://blog.centralcasting.com/jobs-la/",
    "description": (
        "Central Casting posts the background roles it is booking in Los Angeles. "
        "Register with them, then answer the calls that fit you."
    ),
    "bring": "a Central Casting registration",
    "catch": "bookings are not guaranteed; pay depends on the booking",
}


@register_scraper(
    name="centralcasting_onramp",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated link to Central Casting's LA background work board",
    category="perform",
    kind="perform",
    full_snapshot=True,
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=("centralcasting.com",),
)
def search_centralcasting_onramp(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated Central Casting LA card. ``roles`` is ignored."""
    if max_results <= 0:
        return []
    row = {
        "title": _POSTER["title"],
        "company": _POSTER["company"],
        "location": "Los Angeles, CA",
        "url": _POSTER["url"],
        "source": "centralcasting_onramp",
        "vertical": "perform",
        "description": _POSTER["description"],
        "salary_min": None,
        "salary_max": None,
        "date_posted": "",
        "is_rolling": True,
        "first_quest_ok": True,
        "quest": {"bring": _POSTER["bring"], "catch": _POSTER["catch"]},
    }
    logger.info("centralcasting_onramp: 1 curated on-ramp")
    return [row]
