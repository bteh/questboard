"""ICON Clinical Studies (body kind): paid inpatient studies at ICON's US clinics.

ICON runs Phase 1 clinics in Lenexa KS, San Antonio TX and Salt Lake City UT
and lists every open study on ONE server-rendered WordPress page
(live-verified 2026-07-10; robots.txt only disallows /wp-admin/)::

    GET https://iconstudies.com/All-Clinical-Research-Studies/

Each ``div.studies-card`` carries the protocol number ("3954/0090"), a
status pill, the population ("Healthy Participants"), the stated comp
ceiling ("Up to $13500"), the clinic city, a regimen sentence ("1 screening
visit, 1 stay of 18 nights and 2 outpatient visits"), sex and an age band.
"Up to" maps to salary_max ONLY: a ceiling is never a promised floor. Only
cards whose status includes "Enrolling" become rows. The row URL is the
study's public application form
(https://iconstudies.com/<loc>/Clinical-Research-Study/<id>/Application/),
taken from the card's apply link; the page repeats cards across sections,
so rows dedup by URL.

Cards state NO posted date anywhere (page, sitemap, RSS all checked), so
rows never emit date_posted: inventing one would fake a freshness signal
the source does not make (the Doctor of Credit precedent -- saying nothing
beats misleading). The page is the clinics' entire current set, so
full_snapshot=True and a study leaving the page is the expiry signal.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE_URL = "https://iconstudies.com"
_LISTING_URL = f"{_BASE_URL}/All-Clinical-Research-Studies/"

_PRICE_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_AGE_RE = re.compile(r"Age\s+(\d+)\s*-\s*(\d+)", re.IGNORECASE)


def _fetch_listing() -> str | None:
    """GET the all-studies page; None on any failure."""
    try:
        # the shared headers advertise JSON; this page is plain HTML
        resp = requests.get(
            _LISTING_URL, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("ICON studies fetch failed: %s", exc)
        return None


def _text(card, selector: str) -> str:
    node = card.select_one(selector)
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _price_fields(price_text: str) -> dict:
    """Salary keys from the card's stated figure; {} when none.

    "Up to $13500" is a ceiling, so it maps to salary_max ONLY -- promising
    it as a floor would overstate every offer. A bare exact figure (not seen
    live, kept for safety) maps to min=max.
    """
    m = _PRICE_RE.search(price_text)
    if not m:
        return {}
    amount = float(m.group(1).replace(",", ""))
    if "up to" in price_text.lower():
        return {"salary_max": amount, "salary_source": "reported"}
    return {"salary_min": amount, "salary_max": amount, "salary_source": "reported"}


def _normalize_card(card) -> dict | None:
    """Map one studies-card div to a body-kind quest row, or None to skip."""
    status = _text(card, ".studies-card__status-text")
    if "enrolling" not in status.lower():
        return None  # closed / coming-soon studies are not actionable

    btn = card.select_one("a.studies-card__btn")
    href = btn.get("href") if btn else None
    population = _text(card, ".studies-card__title")
    if not href or not population:
        return None

    protocol = _text(card, ".studies-card__number-inner")
    title = f"{population} (Study {protocol})" if protocol else population

    quest: dict = {}
    ages = _AGE_RE.search(_text(card, ".studies-card__age"))
    if ages:
        quest["age_min"] = int(ages.group(1))
        quest["age_max"] = int(ages.group(2))
    sex = _text(card, ".studies-card__sex-text")
    if sex and "/" not in sex:  # "Male/Female" means everyone; say nothing
        quest["sex"] = sex
    if protocol:
        quest["protocol"] = protocol

    row: dict = {
        "title": title,
        "company": "ICON Clinical Studies",
        "location": _text(card, ".studies-card__location-text"),
        "url": urljoin(_BASE_URL, href),
        "source": "iconstudies",
        "vertical": "body",
        # the card's own regimen sentence: visits, nights, follow-ups
        "description": _text(card, ".studies-card__details"),
        # enrolling studies fill on a rolling basis; there is no event date
        "is_rolling": True,
        # healthy-volunteer studies need no prior condition or experience
        "first_quest_ok": "healthy" in population.lower(),
        **_price_fields(_text(card, ".studies-card__price")),
    }
    if quest:
        row["quest"] = quest
    return row


@register_scraper(
    name="iconstudies",
    display_name="ICON Clinical Studies",
    url="https://iconstudies.com",
    description="Paid inpatient clinical studies at ICON's US clinics with the stated comp ceiling",
    category="body",
    kind="body",
    # studies open and close over days, one polite fetch a day
    refresh_hours=24,
    # the page IS the whole current set; leaving it is the expiry signal
    full_snapshot=True,
    allowed_url_hosts=("iconstudies.com",),
    enabled_by_default=False,
)
def search_iconstudies(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch enrolling paid studies from ICON's all-studies page.

    ``roles`` is accepted for the shared scraper calling convention but
    unused: studies are not role-titled, and quest scrapers only run when a
    caller names them.
    """
    logger.info("Fetching enrolling studies from ICON...")
    html = _fetch_listing()
    if not html:
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for card in BeautifulSoup(html, "html.parser").select("div.studies-card"):
        if len(results) >= max_results:
            break
        row = _normalize_card(card)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("ICON: %d enrolling studies", len(results))
    return results
