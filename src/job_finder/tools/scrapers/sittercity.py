"""Sittercity (lookafter kind): babysitting and sitting one-offs by city.

Sittercity publishes its newest postings on public per-city SEO pages
with clean semantic markup (live-verified 2026-07-09)::

    GET https://www.sittercity.com/babysitting-jobs/ca/los-angeles

Each ``article.job-card`` carries the family's own posted rate
("$26–30/hr" in ``job-card__pay``), the neighborhood
(``job-card__distance``), the posting date ("Posted by Francesca C. on
7/9/2026"), and a description. Pay maps to structured hourly figures
only because the poster set the range themselves.

City coverage is a config list, not a vocabulary: ``_DEFAULT_CITY_PATHS``
seeds the big metros and callers can override with the ``city_paths``
kwarg (each entry is the "st/city-slug" tail of the public URL). Each
run costs one request per city and reads the ~15 newest postings there.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://www.sittercity.com"
_CITY_URL = _BASE + "/babysitting-jobs/{path}"

_DEFAULT_CITY_PATHS = (
    "ca/los-angeles",
    "ny/new-york",
    "il/chicago",
    "tx/houston",
    "pa/philadelphia",
    "az/phoenix",
)

# "$26–30/hr" or "$25/hr"; the dash is the site's own en dash or a hyphen
_PAY_RE = re.compile(r"\$(\d+(?:\.\d+)?)(?:\s*[–-]\s*(\d+(?:\.\d+)?))?\s*/hr")
_POSTED_RE = re.compile(r"Posted by\s+(.+?)\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})")


def _card_text(card, selector: str) -> str:
    node = card.select_one(selector)
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _normalize_card(card, city_label: str) -> dict | None:
    """One job-card article to a lookafter-kind quest row, or None."""
    link = card.select_one("a.job-card__title") or card.select_one("h1 a")
    if link is None or not link.get("href"):
        return None
    title = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
    if not title:
        return None
    url = urljoin(_BASE, link["href"])

    distance = _card_text(card, ".job-card__distance")
    location = distance.split("•")[0].strip() if distance else city_label

    row: dict = {
        "title": title,
        "company": "Sittercity",
        "location": location,
        "url": url,
        "source": "sittercity",
        "vertical": "lookafter",
        "description": _card_text(card, ".job-card__description").removesuffix("More").strip(),
    }

    pay = _PAY_RE.search(_card_text(card, ".job-card__pay"))
    if pay:
        lo = float(pay.group(1))
        hi = float(pay.group(2)) if pay.group(2) else lo
        row.update(
            salary_min=lo,
            salary_max=max(lo, hi),
            salary_period="hourly",
            salary_source="reported",
        )

    posted = _POSTED_RE.search(card.get_text(" ", strip=True))
    if posted:
        poster, month, day, year = posted.groups()
        row["date_posted"] = f"{year}-{int(month):02d}-{int(day):02d}"
        row["company"] = f"{poster} via Sittercity"

    quest = {}
    services = _card_text(card, ".job-card__services")
    children = _card_text(card, ".job-card__children")
    if services:
        quest["services"] = services
    if children:
        quest["children"] = children
    if quest:
        row["quest"] = quest
    return row


def _fetch_city(path: str) -> list:
    url = _CITY_URL.format(path=path.strip("/"))
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Sittercity %s fetch failed: %s", path, exc)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select("article.job-card")


@register_scraper(
    name="sittercity",
    display_name="Sittercity",
    url="https://www.sittercity.com",
    description="Babysitting and sitting one-offs with the family's own posted hourly rate, by city",
    category="lookafter",
    kind="lookafter",
    # sits get filled fast and fall off the city page
    stale_after_days=10,
    # the site 429s bursts; one polite sweep a day
    refresh_hours=24,
    allowed_url_hosts=("sittercity.com",),
    enabled_by_default=False,
)
def search_sittercity(
    roles: list[str] | None = None,
    max_results: int = 50,
    city_paths: list[str] | tuple[str, ...] | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch the newest sitting postings from Sittercity city pages.

    ``roles`` is ignored on purpose: sits are not career titles.
    ``city_paths`` overrides the default metro list ("st/city-slug").
    """
    paths = list(city_paths) if city_paths else list(_DEFAULT_CITY_PATHS)
    logger.info("Fetching sitting postings from Sittercity (%d cities)...", len(paths))

    results: list[dict] = []
    seen_urls: set[str] = set()
    for i, path in enumerate(paths):
        if len(results) >= max_results:
            break
        if i:
            time.sleep(1.5)  # the site 429s bursts; one page per beat
        city_label = path.split("/")[-1].replace("-", " ").title()
        for card in _fetch_city(path):
            if len(results) >= max_results:
                break
            row = _normalize_card(card, city_label)
            if row is None or row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(row)

    logger.info("Sittercity: %d postings", len(results))
    return results
