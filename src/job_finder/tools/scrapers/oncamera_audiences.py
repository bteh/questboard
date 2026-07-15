"""On Camera Audiences (camera kind): studio-audience seats at TV tapings.

OCA books audiences for AGT, Jeopardy!, The Price is Right and ~35 other
shows, mostly around Los Angeles. Everything a row needs is server-rendered
(live-verified 2026-07-14)::

    GET https://on-camera-audiences.com/shows/          # div.show-column cards
    GET https://on-camera-audiences.com/shows/<slug>/   # per-show page

An index card carries the show name, a "City / Age: N+" line, a blurb and
the show-page link; the show page adds the pitch prose (#show-info), an
"Event Location" venue block and an "Age restriction" line. The index
repeats current shows in a carousel section, so rows dedup by URL.

robots.txt disallows only /tickets/*, so row URLs are ALWAYS the /shows/
page, never a ticket link (allowed_url_paths pins that contract and the
card parser drops any link outside /shows/).

Concrete taping dates load client-side through a nonce'd admin-ajax call
and never appear in the server HTML; page prose names dates without a year
("Thanksgiving Special! (July 24, 7:30 AM)"), and a date we would have to
guess a year for is a date the source did not state. So a row gets
event_start only when prose states a full month-day-year date that hasn't
passed; everything else is is_rolling. Seats are tickets, not paid gigs:
rows never carry salary keys, and prize copy ("win cash and prizes") is a
game outcome, not comp. The source states no posted dates either, so rows
never emit date_posted.

Show-page fetches wait 1s apart and are capped per run; cards past the cap
still emit from index data alone (name, city, age, blurb).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE_URL = "https://on-camera-audiences.com"
_INDEX_URL = f"{_BASE_URL}/shows/"

_HOST = "on-camera-audiences.com"
_SOURCE = "oncamera_audiences"
_VERTICAL = "camera"

_FETCH_DELAY_S = 1.0
_MAX_SHOW_PAGES = 40
_MAX_DESCRIPTION = 3000

# Index h4: "Los Angeles / Age: 8+", "Kearny, NJ / Age: 16+", " / Age: 21+"
_CITY_AGE_RE = re.compile(r"^(.*?)\s*/\s*Age:\s*(\d+)\+")
# Show page: "Minimum age is 8 years."
_MIN_AGE_RE = re.compile(r"minimum age is\s+(\d+)", re.IGNORECASE)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
# Only a FULL stated date counts ("July 24, 2026"); month-day without a
# year ("July 24, 7:30 AM") would need an invented year, so it never parses.
_FULL_DATE_RE = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")


def _fetch_listing() -> str | None:
    """GET the shows index; None on any failure."""
    try:
        resp = requests.get(
            _INDEX_URL, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("On Camera Audiences index fetch failed: %s", exc)
        return None


def _fetch_show(url: str) -> str | None:
    """GET one show page, waiting the politeness delay first; None on failure."""
    time.sleep(_FETCH_DELAY_S)
    try:
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("On Camera Audiences show fetch failed (%s): %s", url, exc)
        return None


def _show_url_ok(url: str) -> bool:
    """True only for /shows/ pages on the OCA host (robots bans /tickets/*)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.netloc == _HOST
        and parts.path.startswith("/shows/")
        and len(parts.path) > len("/shows/")
    )


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _parse_cards(html: str) -> list[dict]:
    """Unique show cards from the index, in page order, merged across sections."""
    cards: dict[str, dict] = {}
    for div in BeautifulSoup(html, "html.parser").select("div.show-column"):
        url = (div.get("data-link") or "").strip()
        name = _text(div.select_one("h3"))
        if not name or not _show_url_ok(url):
            continue
        city, age_min = "", None
        m = _CITY_AGE_RE.match(_text(div.select_one("h4")))
        if m:
            city = m.group(1).strip()
            age_min = int(m.group(2))
        card = {
            "url": url,
            "name": name,
            "city": city,
            "age_min": age_min,
            "blurb": _text(div.select_one("p.truncate")),
            "genre": (div.get("data-genre") or "").strip(),
            "has_current_tapings": div.get("data-has-current-tapings"),
        }
        prev = cards.get(url)
        if prev is None:
            cards[url] = card
        else:
            # the carousel copy carries the tapings flag; the grid copy may
            # carry a blurb the carousel lacks. Keep whichever field is stated.
            for key, val in card.items():
                if not prev.get(key) and val:
                    prev[key] = val
    return list(cards.values())


def _prose_event_date(text: str, today: date) -> date | None:
    """Earliest stated full date that hasn't passed, or None."""
    upcoming: list[date] = []
    for m in _FULL_DATE_RE.finditer(text):
        month = _MONTHS.get(m.group(1).lower())
        if month is None:
            continue
        try:
            stated = date(int(m.group(3)), month, int(m.group(2)))
        except ValueError:
            continue
        if stated >= today:
            upcoming.append(stated)
    return min(upcoming) if upcoming else None


def _parse_show_page(html: str) -> dict:
    """City, prose, venue lines and stated minimum age from one show page."""
    soup = BeautifulSoup(html, "html.parser")
    detail: dict = {}

    info = soup.select_one("#show-info")
    if info is not None:
        header = info.select_one(".row")
        if header is not None and header.find("h1") is not None:
            detail["city"] = _text(header.find("h2"))
            header.extract()  # keep the title row out of the description
        detail["description"] = _text(info)[:_MAX_DESCRIPTION]

    for h2 in soup.find_all("h2"):
        label = _text(h2).lower()
        if label == "event location":
            block = h2.find_next_sibling("p")
            if block is not None:
                lines = [re.sub(r"\s+", " ", ln).strip() for ln in block.get_text("\n").split("\n")]
                detail["venue_lines"] = [ln for ln in lines if ln]
        elif label == "age restriction":
            m = _MIN_AGE_RE.search(_text(h2.find_next_sibling("p")))
            if m:
                detail["age_min"] = int(m.group(1))
    return detail


def _build_row(card: dict, detail: dict, today: date) -> dict:
    """One index card (plus its show page when fetched) to a camera quest row."""
    name = card["name"]
    venue_lines = detail.get("venue_lines") or []
    venue = venue_lines[0] if venue_lines else ""
    # a stated "TBD - ..." venue is a placeholder, not a bookable place
    company = venue if venue and not venue.lower().startswith("tbd") else name

    quest: dict = {"slug": urlsplit(card["url"]).path.strip("/").split("/")[-1]}
    if card["genre"]:
        quest["genre"] = card["genre"]
    if venue:
        quest["venue"] = venue
    age_min = detail.get("age_min", card["age_min"])
    if age_min is not None:
        quest["age_min"] = age_min
    if card["has_current_tapings"] is not None:
        quest["has_current_tapings"] = card["has_current_tapings"] == "true"

    row: dict = {
        "title": f"Be in the audience: {name}",
        "company": company,
        "location": detail.get("city") or card["city"],
        "url": card["url"],
        "source": _SOURCE,
        "vertical": _VERTICAL,
        "description": detail.get("description") or card["blurb"],
        # audience seats need no experience and nothing to bring but an ID
        "first_quest_ok": True,
        "quest": quest,
    }
    event = _prose_event_date(row["description"], today)
    if event is not None:
        row["event_start"] = event.isoformat()
    else:
        # taping calendars load client-side; the server page states no full date
        row["is_rolling"] = True
    return row


@register_scraper(
    name=_SOURCE,
    display_name="On Camera Audiences",
    url=_BASE_URL,
    description="Studio-audience seats at TV tapings (AGT, Jeopardy!, The Price is Right), mostly LA",
    category="camera",
    kind="camera",
    # the shows index is the source's entire current lineup
    full_snapshot=True,
    # shows come and go over days; one polite crawl a day
    refresh_hours=24,
    allowed_url_hosts=(_HOST,),
    # robots.txt disallows /tickets/*; rows may only point at show pages
    allowed_url_paths=("/shows/",),
    enabled_by_default=False,
)
def search_oncamera_audiences(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch audience-seat quests from On Camera Audiences.

    ``roles`` is accepted for the shared scraper calling convention but
    unused: audience seats are not role-titled, and quest scrapers only run
    when a caller names them.
    """
    logger.info("Fetching shows from On Camera Audiences...")
    html = _fetch_listing()
    if not html:
        return []

    today = datetime.now(timezone.utc).date()
    results: list[dict] = []
    fetched = 0
    for card in _parse_cards(html):
        if len(results) >= max_results:
            break
        detail: dict = {}
        if fetched < _MAX_SHOW_PAGES:
            fetched += 1
            page = _fetch_show(card["url"])
            if page:
                detail = _parse_show_page(page)
        results.append(_build_row(card, detail, today))

    logger.info("On Camera Audiences: %d audience quests", len(results))
    return results
