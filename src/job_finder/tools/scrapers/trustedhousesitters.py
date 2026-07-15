"""TrustedHousesitters (lookafter kind): house and pet sits, barter not pay.

The public assignments index is server-rendered with no login
(live-verified 2026-07-15)::

    GET https://www.trustedhousesitters.com/house-and-pet-sitting-assignments/united-states/

Each page carries 12 ``div[data-testid="ListingCard__container"]`` cards
with the listing's own title, location, image, pet counts, the date range
("31 Jul 2026 - 17 Aug 2026"), and an ``a`` that links to the detail page
at ``/.../l/{id}/``.

ROBOTS (respected): the site disallows ``*/l/*`` and ``/*q=``. So this
crawler fetches only the allowed index pages, harvests each card, and links
OUT to the ``/l/{id}/`` detail URL. It never fetches a ``/l/`` page, and it
never builds the ``?q=`` pagination links. "Pages" here means the geographic
index paths (country, region, city), one allowed page each.

HONESTY: this is barter, never paid. A sit is a free stay in exchange for
caring for the pets and home, so salary is always None and the description
says so plainly. No dollar figure is ever emitted. A dated assignment
carries event_start/event_end and is not rolling; an undated card stays on
the board as is_rolling with no event dates.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://www.trustedhousesitters.com"
_INDEX_URL = _BASE + "/house-and-pet-sitting-assignments/{path}"

# One allowed index page per geographic path; the US country page surfaces the
# newest sits nationwide. Callers widen this for city depth via region_paths.
_DEFAULT_INDEX_PATHS = ("united-states/",)

# robots.txt declares no Crawl-delay; stay polite anyway.
_CRAWL_DELAY_S = 2.0
# Ceiling on index pages fetched per run, independent of max_results.
_PAGE_CAP = 12

# The barter reality, stated plainly and identically on every row: there is
# no pay, only a free stay in exchange for the care.
_BARTER = "No pay. A free stay in exchange for looking after the pets and home."

# "31 Jul 2026 - 17 Aug 2026"; the separator is the site's hyphen or en dash.
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*[–-]\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"
)


def _is_index_url(url: str) -> bool:
    """True only for an allowed index URL: never a /l/ detail or a q= page."""
    parts = urlsplit(url)
    return "/l/" not in parts.path and "q=" not in parts.query


def _fetch_index(path: str) -> list:
    """Fetch one allowed index page and return its listing cards, [] on failure.

    Refuses any URL that robots disallows so no /l/ detail page or q=
    pagination link can ever be requested from here.
    """
    url = _INDEX_URL.format(path=path.strip("/") + "/")
    if not _is_index_url(url):
        logger.warning("TrustedHousesitters refusing disallowed URL: %s", url)
        return []
    try:
        # Ask for HTML explicitly: the shared headers advertise
        # Accept: application/json (the sittercity content-negotiation lesson).
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("TrustedHousesitters %s fetch failed: %s", path, exc)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select('div[data-testid="ListingCard__container"]')


def _pet_phrase(animals: list[tuple[int, str]]) -> str:
    """'2 cats', '1 dog and 1 cat', '' when the card lists no pets."""
    chunks = [f"{n} {kind}" + ("s" if n != 1 else "") for n, kind in animals if n > 0]
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0]
    return ", ".join(chunks[:-1]) + " and " + chunks[-1]


def _card_animals(card) -> list[tuple[int, str]]:
    """(count, animal) pairs from the card's animals list, in card order."""
    animals: list[tuple[int, str]] = []
    for li in card.select('ul[data-testid="animals-list"] li'):
        count_el = li.select_one('span[data-testid="Animal__count"]')
        icon_el = li.select_one('span[data-testid^="animal-icon-"]')
        if not count_el or not icon_el:
            continue
        try:
            count = int(count_el.get_text(strip=True))
        except ValueError:
            continue
        kind = icon_el["data-testid"].removeprefix("animal-icon-").strip()
        if kind:
            animals.append((count, kind))
    return animals


def _card_dates(card) -> tuple[str, str] | None:
    """(event_start, event_end) ISO dates when the card states a range, else None."""
    match = _DATE_RANGE_RE.search(card.get_text(" ", strip=True))
    if not match:
        return None
    try:
        start = datetime.strptime(match.group(1), "%d %b %Y").date()
        end = datetime.strptime(match.group(2), "%d %b %Y").date()
    except ValueError:
        return None
    return start.isoformat(), end.isoformat()


def _card_title(card) -> str:
    node = card.select_one('h3[data-testid="ListingCard__title"]')
    if node:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
    # aria-label reads "listing item for {title}" when the heading is absent
    label = card.get("aria-label") or ""
    return re.sub(r"(?i)^listing item for\s+", "", label).strip()


def _normalize_card(card) -> dict | None:
    """One listing card to a lookafter-kind barter quest row, or None."""
    link = card.select_one('a[href*="/l/"]')
    if link is None or not link.get("href"):
        return None
    title = _card_title(card)
    if not title:
        return None
    # Link OUT to the detail page; drop the site's q= tail for a clean canonical.
    url = urljoin(_BASE, link["href"].split("?", 1)[0])

    loc_el = card.select_one('span[data-testid="ListingCard__location"]')
    location = loc_el.get_text(strip=True) if loc_el else ""

    pets = _pet_phrase(_card_animals(card))
    description = f"Caring for {pets}. {_BARTER}" if pets else _BARTER

    row: dict = {
        "title": title,
        "company": "TrustedHousesitters",
        "location": location,
        "url": url,
        "source": "trustedhousesitters",
        "vertical": "lookafter",
        "description": description,
        # barter, never paid: no dollar figure is ever rendered
        "salary_min": None,
        "salary_max": None,
    }

    quest: dict = {"catch": _BARTER}
    if pets:
        quest["pets"] = pets
    img = card.select_one('div[data-testid="ListingCard__image"] img')
    if img and img.get("src"):
        quest["image"] = img["src"]
    row["quest"] = quest

    dates = _card_dates(card)
    if dates:
        # a dated assignment: real window, not rolling
        row["event_start"], row["event_end"] = dates
        row["is_rolling"] = False
    else:
        # undated card: keep it on the board as a standing barter sit
        row["is_rolling"] = True
    return row


@register_scraper(
    name="trustedhousesitters",
    display_name="TrustedHousesitters",
    url="https://www.trustedhousesitters.com",
    description="House and pet sits offered as barter: a free stay in exchange for caring for the pets and home",
    category="lookafter",
    kind="lookafter",
    # sits fill and their dated window passes; an unconfirmed row shouldn't linger
    stale_after_days=14,
    # the index refreshes through the day; one polite sweep matches that
    refresh_hours=24,
    allowed_url_hosts=("trustedhousesitters.com",),
    enabled_by_default=False,
)
def search_trustedhousesitters(
    roles: list[str] | None = None,
    max_results: int = 50,
    region_paths: list[str] | tuple[str, ...] | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch the newest sits from TrustedHousesitters index pages.

    ``roles`` is ignored on purpose: sits are not career titles.
    ``region_paths`` overrides the default country index with country/region/
    city tails (e.g. "united-states/new-york/brooklyn"). Index pages are
    fetched one per path, sleeping between them and capped at %d per run;
    detail /l/ pages are never fetched (robots).
    """ % _PAGE_CAP
    paths = list(region_paths) if region_paths else list(_DEFAULT_INDEX_PATHS)
    paths = paths[:_PAGE_CAP]
    logger.info("Fetching sits from TrustedHousesitters (%d pages)...", len(paths))

    results: list[dict] = []
    seen_urls: set[str] = set()
    for i, path in enumerate(paths):
        if len(results) >= max_results:
            break
        if i:
            time.sleep(_CRAWL_DELAY_S)
        for card in _fetch_index(path):
            if len(results) >= max_results:
                break
            row = _normalize_card(card)
            if row is None or row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(row)

    logger.info("TrustedHousesitters: %d sits", len(results))
    return results
