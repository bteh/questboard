"""FocusGroups.org -- paid consumer research studies via the rendered listing page.

FocusGroups.org aggregates paid market research: focus groups, 1-on-1
interviews, online surveys, unmoderated studies, product tests, app installs
and clinical trials. robots.txt bans the JSON app endpoints
(app.focusgroups.org), so we politely fetch ONE server-rendered HTML listing
page (https://focusgroups.org/all/) with a standard browser UA. The www host
fails at Cloudflare (526, invalid origin cert); the apex host serves fine.
City pages (/chicago/ etc.) are JS-rendered and empty to a plain GET, so the
apex /all/ page is the only page worth fetching.

Each card carries the study title, the detail link
(/category/<cat>/<slug>/<uuid>/), category + topic pills, a stated posted date
("Posted: MM/DD/YY") and a stated pay chip ("$125", "$100-$125",
"up to $1500", "Varies"). Cards carry no description body, no session length
and no city, so those stay honestly absent. Salary keys are emitted ONLY when
the pay chip parses as an explicit dollar figure; "Varies" and oddball chips
("$60 p/yr", "up to $200+") emit no salary keys and keep the raw chip in
``quest["pay_text"]`` instead. This is a quest scraper (vertical "study"):
explicitly invoked only, never swept into the career pipeline.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _TIMEOUT, date_confidence_for

logger = logging.getLogger(__name__)

_BASE_URL = "https://focusgroups.org"
_LISTING_URL = f"{_BASE_URL}/all/"

# HTML-flavored headers; the shared _utils._HEADERS advertises JSON.
_HTML_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Pay chips as the site prints them. Anchored fullmatch on purpose: anything
# that isn't an explicit per-session dollar figure ("Varies", "$60 p/yr",
# "up to $200+") must NOT become a promised pay number.
_MONEY = r"\$(\d[\d,]*(?:\.\d+)?)"
_PAY_FLAT_RE = re.compile(rf"^{_MONEY}$")
_PAY_RANGE_RE = re.compile(rf"^{_MONEY}\s*-\s*{_MONEY}$")
_PAY_UP_TO_RE = re.compile(rf"^up\s+to\s+{_MONEY}$", re.IGNORECASE)

_POSTED_RE = re.compile(r"Posted:\s*(\d{1,2})/(\d{1,2})/(\d{2,4})")


def _fetch_listing() -> str | None:
    """GET the /all/ listing page; None on any failure."""
    try:
        resp = requests.get(_LISTING_URL, headers=_HTML_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("FocusGroups.org returned %s for %s", resp.status_code, _LISTING_URL)
            return None
        return resp.text
    except requests.RequestException as exc:
        logger.warning("FocusGroups.org fetch failed: %s", exc)
        return None


def _parse_pay(text: str) -> tuple[float | None, float | None]:
    """(min, max) dollars from a pay chip, or (None, None) when not explicit.

    '$38' -> (38, 38); '$100-$125' -> (100, 125); 'up to $1500' -> (None, 1500).
    Everything else, including 'Varies', is not a stated per-session figure.
    """
    text = text.strip()
    m = _PAY_FLAT_RE.fullmatch(text)
    if m:
        val = float(m[1].replace(",", ""))
        return val, val
    m = _PAY_RANGE_RE.fullmatch(text)
    if m:
        lo = float(m[1].replace(",", ""))
        hi = float(m[2].replace(",", ""))
        return (lo, hi) if lo <= hi else (hi, lo)
    m = _PAY_UP_TO_RE.fullmatch(text)
    if m:
        return None, float(m[1].replace(",", ""))
    return None, None


def _posted_to_iso(text: str) -> str:
    """'Posted: 07/08/26' -> '2026-07-08'; '' when the chip is absent/odd."""
    m = _POSTED_RE.search(text)
    if not m:
        return ""
    month, day, year = int(m[1]), int(m[2]), int(m[3])
    if year < 100:
        year += 2000
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _text(node) -> str:
    """Whitespace-collapsed text of a bs4 node ('' for None)."""
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _parse_cards(html: str) -> list[dict]:
    """Extract the study cards from the listing page HTML.

    Cards are ``<a href="/category/.../<uuid>/"><div class="study-pannel">``.
    Selecting on the panel div (not on hrefs) keeps nav /category/ links out.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards: list[dict] = []
    for panel in soup.select("div.study-pannel"):
        anchor = panel.find_parent("a")
        href = anchor.get("href") if anchor else None
        if not href:
            continue
        cards.append({
            "title": _text(panel.select_one(".study-title")),
            "url": urljoin(_BASE_URL, href),
            "category": _text(panel.select_one(".pill.category")),
            "topic": _text(panel.select_one(".pill.topic")),
            "featured": panel.select_one(".pill.featured") is not None,
            "pay_text": _text(panel.select_one(".details .dollars")),
            "posted_text": _text(panel.select_one(".details .date-posted")),
        })
    return cards


def _normalize_card(card: dict) -> dict | None:
    """Map one parsed card to a quest row, or None when unusable."""
    title = card.get("title") or ""
    url = card.get("url") or ""
    if not title or not url:
        return None

    category = card.get("category") or ""
    topic = card.get("topic") or ""
    if topic.lower() == "none":  # the site's literal placeholder pill
        topic = ""
    pay_text = card.get("pay_text") or ""

    # "Online" only when the card itself says so (category or title). Cards
    # never state a city, and in-person vs online is otherwise unknowable here.
    online = "online" in f"{category} {title}".lower()

    quest: dict = {}
    if category:
        quest["category"] = category
    if topic:
        quest["topic"] = topic
    if card.get("featured"):
        quest["featured"] = True
    if pay_text and pay_text.lower() != "varies":
        quest["pay_text"] = pay_text
    if online:
        quest["format"] = "online"

    parts = [p for p in (
        f"Category: {category}" if category else "",
        f"Topic: {topic}" if topic else "",
        f"Pay: {pay_text}" if pay_text else "",
    ) if p]

    row: dict = {
        "title": title,
        "company": "FocusGroups.org",
        "location": "Online" if online else "",
        "url": url,
        "source": "focusgroups_org",
        "vertical": "study",
        # Cards carry no description body; surface the structured chips.
        "description": "; ".join(parts),
        # Consumer research needs no prior experience or portfolio; screeners
        # gate demographics, not track record.
        "first_quest_ok": True,
        "quest": quest,
    }

    date_posted = _posted_to_iso(card.get("posted_text") or "")
    if date_posted:
        row["date_posted"] = date_posted
        row["date_confidence"] = date_confidence_for(date_posted)

    # Omit any salary key we have no figure for: "up to $X" has no floor, and
    # a salary_min=None key downstream reads as stated pay data.
    lo, hi = _parse_pay(pay_text)
    if lo is not None or hi is not None:
        if lo is not None:
            row["salary_min"] = lo
        if hi is not None:
            row["salary_max"] = hi
        row["salary_period"] = "session"
        row["salary_source"] = "reported"

    return row


@register_scraper(
    name="focusgroups_org",
    display_name="FocusGroups.org",
    url="https://focusgroups.org",
    description="Paid focus groups, interviews and consumer research studies",
    category="study",
    # new groups post on business days
    refresh_hours=24,
    allowed_url_hosts=("focusgroups.org",),
    enabled_by_default=False,
    vertical="study",
    # focus groups recruit for a few weeks at most
    stale_after_days=30,
)
def search_focusgroups_org(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch paid research studies from the FocusGroups.org listing page.

    ``roles`` is accepted for the shared scraper calling convention but unused:
    studies are not role-titled, and quest scrapers only run when a caller
    names them.
    """
    logger.info("Fetching paid research studies from FocusGroups.org...")
    html = _fetch_listing()
    if not html:
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for card in _parse_cards(html):
        if len(results) >= max_results:
            break
        row = _normalize_card(card)
        if not row or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("FocusGroups.org: found %d studies", len(results))
    return results
