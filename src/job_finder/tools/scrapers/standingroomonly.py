"""Standing Room Only, US TV audience seats + court-show casting (camera vertical).

Two public, unauthenticated endpoints feed this scraper (both live-verified):

1. ``https://app.standingroomonly.tv/api/shows`` is the live booking list that
   the /shows/ page renders. Each row carries ``project_id``, ``public_name``,
   prose ``project_notes``, and a ``formatted_datetime`` like
   ``"7/08/26 9:15 AM PDT"``. Rows titled "... Sign Up" / "Rush Call" /
   "Onboarding" are standing lists parked on an end-of-year placeholder date,
   so they are emitted as ``is_rolling`` with no ``event_start``.

2. ``https://standingroomonly.tv/wp-json/wp/v2/pages`` holds the WordPress
   pages (posts is empty). Most pages are platform plumbing (payroll, I-9,
   FAQ); show recruitment pages are picked out by their signup CTAs (a
   forms.gle signup link, "Sign Up Now" / "RSVP" / "Actors Wanted" copy,
   verified to select exactly the 7 show pages out of 43 live pages). Dated
   campaign pages state their taping date only in prose ("Date: Wednesday,
   April 1st, 2026"); pages whose date has passed are dropped (SRO leaves old
   campaigns up), and undated casting pages are standing signups.

Pay ("$20/hr") appears only in prose, never structured, so no salary keys are
emitted: quest verticals never mine pay from description text.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _strip_html

logger = logging.getLogger(__name__)

_SHOWS_API_URL = "https://app.standingroomonly.tv/api/shows"
_PAGES_URL = "https://standingroomonly.tv/wp-json/wp/v2/pages"

_SOURCE = "standingroomonly"
_VERTICAL = "camera"
_COMPANY = "Standing Room Only"

# "7/08/26 9:15 AM PDT" is the API's only datetime shape.
_SHOW_DATETIME_RE = re.compile(
    r"^\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s+(\d{1,2}):(\d{2})\s*(AM|PM)\s+([A-Z]{2,4})\s*$",
    re.IGNORECASE,
)
_TZ_OFFSET_HOURS = {
    "PST": -8, "PDT": -7, "MST": -7, "MDT": -6,
    "CST": -6, "CDT": -5, "EST": -5, "EDT": -4,
}

# Standing lists on the API (parked on a 12/31 placeholder date) name
# themselves: "... Sign Up", "... Rush Call", "RUSH CALLS", "... Onboarding".
_STANDING_TITLE_RE = re.compile(r"sign\s*-?\s*up|rush\s*call|onboarding", re.IGNORECASE)
# Onboarding rows are for already-booked members, not open first quests.
_RESTRICTED_TITLE_RE = re.compile(r"onboarding", re.IGNORECASE)

_PAREN_LOCATION_RE = re.compile(r"\(([^()]+)\)\s*$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Month-name prose dates on campaign pages ("Date: Wednesday, April 1st, 2026").
# "februrary" is a live typo on the fox page; without it that page never dates.
_MONTHS = {
    "january": 1, "february": 2, "februrary": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
    "october": 10, "november": 11, "december": 12,
}
_PROSE_DATE_RE = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b")

# "Location: Atlanta, Georgia <calendar emoji> ...": capture until the next
# emoji marker (Misc Technical, Misc Symbols, and the SMP emoji blocks).
_LOCATION_LINE_RE = re.compile(
    r"location:\s*([^⌀-⏿☀-➿\U0001F300-\U0001FAFF]{1,80})",
    re.IGNORECASE,
)

# CTA signals that mark a WP page as a show recruitment page. "casting" and
# "register now" alone are too noisy (home/covid/privacy pages carry both).
_PAGE_CTA_PHRASES = ("sign up now", "rsvp", "actors wanted")
# Platform pages that must never be emitted even if their copy gains a CTA.
_PLATFORM_SLUGS = frozenset({
    "shows", "register", "apply", "home", "faq", "profile", "payroll",
})


def _parse_show_datetime(text: str | None) -> datetime | None:
    """Parse the API's ``formatted_datetime`` into an aware datetime, or None."""
    if not text:
        return None
    m = _SHOW_DATETIME_RE.match(text)
    if not m:
        return None
    month, day, year = int(m[1]), int(m[2]), int(m[3])
    hour, minute = int(m[4]) % 12, int(m[5])
    if m[6].upper() == "PM":
        hour += 12
    offset = _TZ_OFFSET_HOURS.get(m[7].upper())
    if offset is None:
        return None  # unknown zone: better no event date than a wrong one
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, hour, minute,
                        tzinfo=timezone(timedelta(hours=offset)))
    except ValueError:
        return None


def _fetch_api_shows() -> list[dict]:
    """The live booking list; [] on any failure."""
    data = _get_json(_SHOWS_API_URL)
    shows = data.get("shows") if isinstance(data, dict) else None
    if not isinstance(shows, list):
        return []
    return [s for s in shows if isinstance(s, dict)]


def _fetch_pages() -> list[dict]:
    """All WordPress pages; [] on any failure."""
    data = _get_json(_PAGES_URL, params={"per_page": "100"})
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict)]


def _normalize_api_show(show: dict) -> dict | None:
    """Map one /api/shows row to the quest contract, or None."""
    title = (show.get("public_name") or "").strip()
    if not title:
        return None
    project_id = show.get("project_id")
    datetime_text = show.get("formatted_datetime") or ""

    # The site's own per-show deep-link form (its campaign pages use it too).
    if project_id:
        slug = _SLUG_RE.sub("-", title.lower()).strip("-")
        url = f"https://standingroomonly.tv/show/{project_id}/{slug}"
    else:
        url = "https://standingroomonly.tv/shows/"

    m = _PAREN_LOCATION_RE.search(title)
    location = m[1].strip() if m else ""

    actions = show.get("actions") or {}
    row: dict = {
        "title": title,
        "company": _COMPANY,
        "location": location,
        "url": url,
        "source": _SOURCE,
        "vertical": _VERTICAL,
        "description": _strip_html(show.get("project_notes") or ""),
        "quest": {
            "project_id": project_id,
            "datetime_text": datetime_text,
            "can_apply": bool(actions.get("can_apply")) if isinstance(actions, dict) else False,
        },
    }
    if _STANDING_TITLE_RE.search(title):
        row["is_rolling"] = True  # placeholder-dated standing list, not a taping
    else:
        start = _parse_show_datetime(datetime_text)
        if start is not None:
            row["event_start"] = start.isoformat()
    if not _RESTRICTED_TITLE_RE.search(title):
        # Open public signup: audience seats and non-union litigant roles
        # explicitly welcome first-timers (repeat litigants are turned away).
        row["first_quest_ok"] = True
    return row


def _parse_prose_event_date(text: str) -> date | None:
    """First month-name date stated in page prose, or None."""
    for m in _PROSE_DATE_RE.finditer(text):
        month = _MONTHS.get(m[1].lower())
        if month is None:
            continue
        try:
            return date(int(m[3]), month, int(m[2]))
        except ValueError:
            return None
    return None


def _page_is_show_listing(page: dict, html: str, text_lower: str) -> bool:
    """True when a WP page is a show recruitment page, not platform plumbing."""
    if (page.get("slug") or "") in _PLATFORM_SLUGS:
        return False
    if "forms.gle" in html:
        return True
    return any(phrase in text_lower for phrase in _PAGE_CTA_PHRASES)


def _normalize_page(page: dict, today: date) -> dict | None:
    """Map one WP page to the quest contract; None for non-show or stale pages."""
    html = ""
    content = page.get("content")
    if isinstance(content, dict):
        html = content.get("rendered") or ""
    title_field = page.get("title")
    title = _strip_html(title_field.get("rendered") or "") if isinstance(title_field, dict) else ""
    url = page.get("link") or ""
    if not html or not title or not url:
        return None

    text = _strip_html(html)
    if not _page_is_show_listing(page, html, text.lower()):
        return None

    m = _LOCATION_LINE_RE.search(text)
    location = m[1].strip(" .,;:") if m else ""

    row: dict = {
        "title": title,
        "company": _COMPANY,
        "location": location,
        "url": url,
        "source": _SOURCE,
        "vertical": _VERTICAL,
        "description": text,
        "first_quest_ok": True,
        "quest": {
            "page_slug": page.get("slug") or "",
            "application_route": "google_form" if "forms.gle" in html else "sro_profile",
        },
    }
    event_date = _parse_prose_event_date(text)
    if event_date is not None:
        if event_date < today:
            return None  # old campaign page SRO left up
        row["event_start"] = event_date.isoformat()
    else:
        row["is_rolling"] = True  # undated standing signup (court casting etc.)
    return row


@register_scraper(
    name="standingroomonly",
    display_name="Standing Room Only",
    url="https://standingroomonly.tv",
    description="US TV audience seats and court-show casting calls from Standing Room Only",
    category="camera",
    vertical="camera",
    # audience calls post days ahead
    refresh_hours=24,
    allowed_url_hosts=("standingroomonly.tv",),
    enabled_by_default=False,
)
def search_standingroomonly(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch audience-seat and casting quests from Standing Room Only.

    ``roles`` is accepted for registry-call compatibility but ignored: camera
    quests are not career-role shaped, and this scraper only runs when a
    caller names it explicitly.
    """
    logger.info("Fetching shows from Standing Room Only...")
    today = datetime.now(timezone.utc).date()
    results: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for show in _fetch_api_shows():
        if len(results) >= max_results:
            break
        row = _normalize_api_show(show)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    # Newest-edited first so title dedup keeps the freshest of SRO's duplicate
    # campaign landing pages (court / court-2 / project-casting share a title).
    pages = sorted(_fetch_pages(), key=lambda p: str(p.get("modified") or ""), reverse=True)
    for page in pages:
        if len(results) >= max_results:
            break
        row = _normalize_page(page, today)
        if row is None or row["url"] in seen_urls:
            continue
        title_key = row["title"].lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("Standing Room Only: found %d camera quests", len(results))
    return results
