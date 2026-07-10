"""1iota (camera vertical): free TV studio-audience seats via the open ticket API.

1iota fills studio audiences for talk shows, late-night tapings, and fan
events. The production ticket endpoint

    https://prod-tickets.1iota.com/api/event/list

is open (no auth) and returns every listed event as a flat JSON array. Each
event carries the show title, city/state, the taping start in UTC
(``startDateUtc``, with or without a trailing 'Z'), age limits, a per-user
ticket cap, and sold-out / coming-soon flags. Audience seats are UNPAID, so
rows never carry salary keys. The user-facing deep link is
``https://1iota.com/event/<eventId>``.

Module is named ``oneiota`` because a module name cannot start with a digit;
the registered scraper name stays ``"1iota"``.
"""

from __future__ import annotations

import logging
from html import unescape

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _parse_posted_date, _strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://prod-tickets.1iota.com/api/event/list"
_EVENT_URL = "https://1iota.com/event/{event_id}"


def _normalize_event(event: dict) -> dict | None:
    """Map one 1iota event object to a camera-vertical quest row, or None."""
    event_id = event.get("eventId")
    show = (event.get("title") or "").strip()
    if not isinstance(event_id, int) or not show:
        return None

    subtitle = (event.get("subTitle") or "").strip()
    title = f"Audience seat: {show}"
    if subtitle:
        title = f"{title} ({subtitle})"

    city = (event.get("city") or "").strip()
    state = (event.get("state") or "").strip()
    # ``where`` is already display-ready ("New York, NY", "Anywhere").
    location = (event.get("where") or "").strip() or ", ".join(
        p for p in (city, state) if p
    )

    # Descriptions arrive as HTML, often with entity-escaped tags
    # (``&lt;p&gt;...``), so unescape before stripping.
    raw_desc = event.get("description") or ""
    description = _strip_html(unescape(raw_desc)) if raw_desc else ""

    quest: dict = {"show": show}
    if city:
        quest["city"] = city
    age_min = event.get("minimumAgeLimit")
    if isinstance(age_min, int) and age_min > 0:
        quest["age_min"] = age_min
    max_tickets = event.get("maxTickets")
    if isinstance(max_tickets, int) and max_tickets > 0:
        quest["max_tickets"] = max_tickets
    if event.get("isComingSoon"):
        quest["coming_soon"] = True

    row: dict = {
        "title": title,
        "company": "1iota",
        "location": location,
        "url": _EVENT_URL.format(event_id=event_id),
        "source": "1iota",
        "vertical": "camera",
        "description": description,
        # Sitting in an audience needs no experience. No date_posted: the API
        # never states when an event was listed, and no salary keys ever.
        "first_quest_ok": True,
        "quest": quest,
    }

    # startDateUtc is the real taping datetime. The API sometimes omits the
    # trailing 'Z' but the field is UTC either way.
    start = _parse_posted_date(event.get("startDateUtc"))
    if start is not None:
        row["event_start"] = start.isoformat()
    return row


@register_scraper(
    name="1iota",
    display_name="1iota (TV audience seats)",
    url="https://1iota.com",
    description="Free studio-audience seats for TV tapings and fan events",
    category="camera",
    vertical="camera",
    # tapings announce days ahead
    refresh_hours=24,
    allowed_url_hosts=("1iota.com",),
    enabled_by_default=False,
)
def search_oneiota(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch free TV-audience events from 1iota's open ticket API.

    Role keywords are ignored on purpose: camera quests are shows, not job
    titles, and filtering them against career roles would drop everything.
    Sold-out events are skipped because they are no longer requestable.
    """
    logger.info("Fetching audience events from 1iota...")
    data = _get_json(_API_URL)
    if not isinstance(data, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for event in data:
        if len(results) >= max_results:
            break
        if not isinstance(event, dict) or event.get("isSoldOut"):
            continue
        row = _normalize_event(event)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("1iota: found %d open audience events", len(results))
    return results
