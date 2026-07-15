"""Curated Rover on-ramp (lookafter kind): start dog sitting or walking.

Rover has no public job feed and its pages sit behind Cloudflare, so it
cannot be scraped: https://www.rover.com/become-a-sitter/ returns a
Cloudflare managed challenge (403 with cf-mitigated: challenge, verified
2026-07-15), and even /robots.txt serves the JS challenge. So this is a
standing on-ramp, one row, not a scraper. The data below IS the content;
the search function makes no network calls.

HONESTY: Rover sitters set their own rates and Rover takes a service fee,
so no earning amount is invented (salary stays None). The one poster links
to Rover's own start page. A later affiliate tag is wired by the
orchestrator in the registry, never here.
"""

from __future__ import annotations

import logging

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_POSTER = {
    "title": "Start earning as a dog sitter or walker on Rover",
    "company": "Rover",
    "url": "https://www.rover.com/become-a-sitter/",
    "description": "Sign up on Rover to look after and walk dogs for people near you.",
    # what starting genuinely takes, in Rover's own terms
    "bring": "a profile and a background check",
    # the fee-and-rates reality, stated plainly (Rover sets no fixed pay)
    "catch": "Rover takes a service fee; you set your own rates",
}


@register_scraper(
    name="rover_onramp",
    display_name="Questboard",
    url="https://questboard.io",
    description="Curated on-ramp to start dog sitting or walking on Rover",
    category="lookafter",
    kind="lookafter",
    # one curated row is the source's entire set, so absence proves removal
    full_snapshot=True,
    # content changes only when this file is edited; a weekly sweep keeps the
    # freshness contract satisfied without hammering anything
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=("rover.com",),
)
def search_rover_onramp(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return the curated Rover on-ramp quest.

    ``roles`` is ignored on purpose: on-ramps are not career titles.
    """
    if max_results <= 0:
        return []
    row = {
        "title": _POSTER["title"],
        "company": _POSTER["company"],
        # do-anywhere on-ramp: carries no location
        "location": "",
        "url": _POSTER["url"],
        "source": "rover_onramp",
        "vertical": "lookafter",
        "description": _POSTER["description"],
        # never invent pay: Rover sitters set their own rates
        "salary_min": None,
        "salary_max": None,
        # standing quest: no dates, no invented freshness
        "date_posted": "",
        "is_rolling": True,
        # signing up needs no prior gig anywhere
        "first_quest_ok": True,
        "quest": {"bring": _POSTER["bring"], "catch": _POSTER["catch"]},
    }
    logger.info("rover_onramp: 1 curated on-ramp")
    return [row]
