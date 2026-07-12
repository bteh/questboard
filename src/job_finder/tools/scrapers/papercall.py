"""PaperCall (speak kind): open conference and meetup CFPs, paginated directory.

papercall.io publishes its event directory as public paginated HTML
(live-probed 2026-07-12; robots.txt fully permissive)::

    GET https://www.papercall.io/events?page=N   -> 20 events per page,
    ~12 pages, last page partial

Each ``div.event-list-detail`` card links the event's own papercall.io
CFP page — the page with the submit button — and that link is the row
url. The card states the CFP close time as ``<time datetime="...">``,
which becomes the quest's apply_by; rows whose deadline has already
passed are dropped, and so are "CFP is open" cards with no deadline
(that class outlives its events). Cards with neither are events whose CFP is not
open right now, so they never become rows.

The honesty gold is the perk flag: "This CFP offers travel assistance."
When present it rides in ``quest.pay_note`` as "CFP offers travel
assistance (as stated)". It is a perk statement, never pay: speaking
slots are not paid gigs and speak rows never carry salary keys
(callingallpapers precedent).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://www.papercall.io"
_EVENTS_URL = _BASE + "/events"
_PAGE_SIZE = 20   # a shorter page is the directory's last
_MAX_PAGES = 30   # hard stop if the short-page signal ever breaks
_PAGE_SLEEP = 1.0

_TRAVEL_RE = re.compile(r"offers travel assistance", re.IGNORECASE)
_TRAVEL_NOTE = "CFP offers travel assistance (as stated)"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_close(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _title_link(card):
    for link in card.select("h3.event__title a[href]"):
        if "/pricing" in link["href"]:
            continue  # the "Pro Event" tag, not the event
        return link
    return None


def _event_dates_text(card) -> str:
    for h4 in card.select("h4"):
        strong = h4.find("strong")
        if strong and "Event Dates" in strong.get_text():
            text = h4.get_text(" ", strip=True)
            return re.sub(r"^.*Event Dates:\s*", "", text).strip()
    return ""


def _normalize_card(card, now: datetime) -> dict | None:
    """One directory card to a speak-kind quest row, or None to skip."""
    link = _title_link(card)
    if link is None:
        return None
    url = urljoin(_BASE, link["href"])

    name_node = card.select_one("var.atc_title")
    name = name_node.get_text(strip=True) if name_node else link.get_text(" ", strip=True)
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return None

    time_node = card.select_one("time[datetime]")
    deadline_raw = time_node.get("datetime", "") if time_node else ""
    deadline = _parse_close(deadline_raw) if deadline_raw else None
    if deadline is None or deadline < now:
        # Only a future close time proves the CFP is live. "CFP is open"
        # with no deadline is the recurring-meetup class whose pages
        # outlive the event (a 2020 conference wore that label on the
        # live board, 2026-07-12); unverifiable liveness never publishes.
        return None
    from job_finder.tools.scrapers._speak import is_sentinel_deadline

    if is_sentinel_deadline(deadline):
        # a placeholder 2050-01-01 close is a rolling call, not a real
        # deadline (audit 2026-07-12: "Web3 London" wore it); a fake date
        # fails the real-date contract as surely as no date
        return None

    loc_node = card.select_one("var.atc_location")
    location = loc_node.get_text(strip=True) if loc_node else ""
    dates_text = _event_dates_text(card)

    parts: list[str] = []
    quest: dict = {}
    if deadline is not None:
        quest["apply_by"] = deadline_raw
        parts.append(f"CFP closes {deadline.date().isoformat()}.")
    if dates_text:
        quest["event_dates"] = dates_text
        parts.append(f"Event dates: {dates_text}.")
    if card.find(attrs={"title": _TRAVEL_RE}) is not None:
        quest["pay_note"] = _TRAVEL_NOTE
        parts.append(_TRAVEL_NOTE + ".")

    row: dict = {
        "title": f"Speak at {name}",
        "company": name,
        "location": location or "Online",
        "is_remote": not location or location.lower() == "online",
        "url": url,
        "source": "papercall",
        "vertical": "speak",
        "description": " ".join(parts),
    }
    if quest:
        row["quest"] = quest
    return row


def _fetch_page(page: int) -> list:
    try:
        # the shared headers ask for JSON; this site serves HTML
        resp = requests.get(
            _EVENTS_URL,
            params={"page": page},
            headers={**_HEADERS, "Accept": "text/html"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("PaperCall page %d fetch failed: %s", page, exc)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select("div.event-list-detail")


@register_scraper(
    name="papercall",
    display_name="PaperCall",
    url="https://www.papercall.io",
    description="Open conference and meetup CFPs with stated deadlines and the travel-assistance flag",
    category="speak",
    kind="speak",
    # one sweep of the directory IS the entire open-CFP set
    full_snapshot=True,
    # CFPs open and close on a daily rhythm at most; one polite sweep a day
    refresh_hours=24,
    enabled_by_default=False,
    allowed_url_hosts=("papercall.io",),
)
def search_papercall(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch open CFPs from the PaperCall event directory.

    ``roles`` is ignored on purpose: CFPs are not career titles.
    """
    logger.info("Fetching open CFPs from PaperCall...")
    now = _utcnow()

    results: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        if len(results) >= max_results:
            break
        if page > 1:
            time.sleep(_PAGE_SLEEP)  # stay polite between pages
        cards = _fetch_page(page)
        if not cards:
            break
        for card in cards:
            if len(results) >= max_results:
                break
            row = _normalize_card(card, now)
            if row is None or row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(row)
        if len(cards) < _PAGE_SIZE:
            break  # a short page is the directory's last

    logger.info("PaperCall: %d open CFPs", len(results))
    return results
