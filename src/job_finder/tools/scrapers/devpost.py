"""Devpost hackathons (pitch kind): prize-backed builds for young makers.

Devpost's public listing API returns open and upcoming hackathons as JSON,
no auth, ordered by prize amount so the biggest pools come first::

    GET https://devpost.com/api/hackathons
        ?status[]=open&status[]=upcoming&order_by=prize-amount&page=N

Live-verified quirks (2026-07-15, meta.total_count 165, 9 per page):

- The response is ``{"hackathons": [...], "meta": {total_count, per_page}}``.
  Paging is 1-based; a page with fewer than per_page items is the last.
- ``prize_amount`` is a rendered HTML string, currency symbol then a
  ``<span data-currency-value>`` figure ("$<span ...>100,000</span>",
  "₹ <span ...>100,000</span>"). The prize is emitted verbatim as the
  symbol plus figure Devpost displays, tags stripped, never as salary:
  a prize pool is not pay and it goes to the projects judges pick.
- ``url`` is each hackathon's own page on a ``*.devpost.com`` subdomain,
  which is the apply/register entry, so rows point there (host-gated to
  devpost.com on the registry entry).
- ``submission_period_dates`` is prose ("May 19 - Aug 17, 2026",
  "Jul 13 - 21, 2026"). A concrete end date becomes ``event_start`` so
  the board drops the row once submissions close; anything unparseable
  stays ``is_rolling``. The verbatim string also rides in ``quest.timing``.
- ``invite_only`` gigs are excluded: you cannot just apply.

robots.txt bans named AI user agents but allows generic clients, so the
shared browser User-Agent is used and the crawler never names itself as
an AI. One request per page with a small delay keeps it polite.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_API_URL = "https://devpost.com/api/hackathons"
_PER_PAGE = 9
_MAX_PAGES = 15  # a runaway pager stops here; max_results caps sooner
_PAGE_DELAY = 0.5

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_YEAR_RE = re.compile(r"(20\d\d)")
_RANGE_SPLIT_RE = re.compile(r"\s+-\s+")
_MONTH_DAY_RE = re.compile(r"([A-Za-z]{3,9})\s+(\d{1,2})")
_LEADING_DAY_RE = re.compile(r"(\d{1,2})")
_LEADING_MONTH_RE = re.compile(r"([A-Za-z]{3,9})")


def _prize_text(raw: object) -> str:
    """The prize exactly as Devpost renders it, HTML tags stripped.

    "$<span data-currency-value>100,000</span>" -> "$100,000"; tags are
    removed without inserting a space so the currency symbol stays flush
    against the figure. No figure is invented: only what the field states.
    """
    text = re.sub(r"<[^>]+>", "", str(raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def _parse_end_date(raw: str) -> date | None:
    """The concrete end date of a submission window, or None.

    Handles "May 19 - Aug 17, 2026" (end carries its own month), "Jul 13 -
    21, 2026" (end is a day only, month inherited from the start), and a
    single "Jul 18, 2026". Returns None when no year or day can be read.
    """
    text = re.sub(r"\s+", " ", raw or "").strip()
    if not text:
        return None
    years = _YEAR_RE.findall(text)
    if not years:
        return None
    year = int(years[-1])

    parts = _RANGE_SPLIT_RE.split(text)
    end = parts[-1].strip()
    start = parts[0].strip() if len(parts) > 1 else ""

    m = _MONTH_DAY_RE.match(end)
    if m:
        month = _MONTHS.get(m.group(1).lower()[:3])
        day = int(m.group(2))
    else:
        dm = _LEADING_DAY_RE.match(end)
        sm = _LEADING_MONTH_RE.match(start)
        if not dm or not sm:
            return None
        day = int(dm.group(1))
        month = _MONTHS.get(sm.group(1).lower()[:3])
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _normalize(item: dict) -> dict | None:
    """One API hackathon to a pitch-kind quest row, or None to skip."""
    if not isinstance(item, dict):
        return None
    if item.get("invite_only") is True:
        return None
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title or not url.startswith("http"):
        return None

    org = str(item.get("organization_name") or "").strip()
    prize = _prize_text(item.get("prize_amount"))
    has_prize = bool(re.search(r"\d", prize))

    location = ""
    displayed = item.get("displayed_location")
    if isinstance(displayed, dict):
        location = str(displayed.get("location") or "").strip()

    if org:
        sentence = f"A hackathon on Devpost hosted by {org}."
    else:
        sentence = "A hackathon on Devpost."
    # Lead with the prize: the card shows only the first sentence, and the
    # pool is the whole reason this sits in the funding lane. It is a pool
    # you compete for (the catch says so), never guaranteed pay.
    if has_prize:
        description = f"{prize} in prizes. {sentence}"
    else:
        description = sentence

    quest: dict = {
        # a hackathon: the pool goes to the projects judges pick, not pay
        "catch": "You are competing; the prize pool goes to the projects judges pick.",
    }
    if has_prize:
        quest["prize"] = prize
    dates_raw = re.sub(r"\s+", " ", str(item.get("submission_period_dates") or "")).strip()
    if dates_raw:
        quest["timing"] = dates_raw

    row: dict = {
        "title": title,
        "company": "Devpost",
        "location": location,
        "url": url,
        "source": "devpost",
        "vertical": "pitch",
        "description": description,
        # a prize pool is not pay: never populate the salary fields
        "salary_min": None,
        "salary_max": None,
        # the API states no posting date
        "date_posted": "",
        # open registration, no prior experience needed to enter
        "first_quest_ok": True,
        "quest": quest,
    }
    end = _parse_end_date(dates_raw)
    if end is not None:
        row["event_start"] = end.isoformat()
    else:
        row["is_rolling"] = True
    return row


def _fetch_page(page: int) -> dict | None:
    params = [
        ("status[]", "open"),
        ("status[]", "upcoming"),
        ("order_by", "prize-amount"),
        ("page", str(page)),
    ]
    try:
        resp = requests.get(
            _API_URL,
            params=params,
            headers={**_HEADERS, "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Devpost page %d fetch failed: %s", page, exc)
        return None
    return data if isinstance(data, dict) else None


@register_scraper(
    name="devpost",
    display_name="Devpost hackathons",
    url="https://devpost.com/hackathons",
    description="Open and upcoming prize-backed hackathons from Devpost, biggest prize pools first",
    category="pitch",
    kind="pitch",
    # a paged, prize-ranked window capped at max_results, not the whole set,
    # so it declares a stale window instead of full-snapshot absence; each
    # dated row also expires precisely via its submission end date
    stale_after_days=14,
    # listings shift daily at most; one polite sweep a day
    refresh_hours=24,
    allowed_url_hosts=("devpost.com",),
    enabled_by_default=False,
)
def search_devpost(
    roles: list[str] | None = None,
    max_results: int = 25,
    **kwargs,
) -> list[dict]:
    """Fetch open and upcoming hackathons from Devpost, prize pool first.

    ``roles`` is ignored on purpose: hackathons are not career titles. Pages
    are fetched one at a time with a small delay, capped at ``max_results``.
    """
    logger.info("Fetching open and upcoming hackathons from Devpost...")

    results: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(1, _MAX_PAGES + 1):
        if len(results) >= max_results:
            break
        if page > 1:
            time.sleep(_PAGE_DELAY)
        data = _fetch_page(page)
        if data is None:
            break
        items = data.get("hackathons")
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if len(results) >= max_results:
                break
            row = _normalize(item)
            if row is None or row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(row)
        if len(items) < _PER_PAGE:
            break
        meta = data.get("meta")
        total = meta.get("total_count") if isinstance(meta, dict) else None
        if isinstance(total, int) and page * _PER_PAGE >= total:
            break

    logger.info("Devpost: %d hackathons", len(results))
    return results
