"""Fortrea Clinical Trials (body kind): phase-1 studies at Fortrea's own units.

The US browse page is a server-rendered Drupal table; plain requests get
a 200 and robots.txt permits it (live-verified 2026-07-10)::

    GET https://www.fortreaclinicaltrials.com/en-us/clinical-research/browse-studies

There is no pagination: one fetch is the entire current set (six studies
that day, across the Dallas TX, Daytona Beach FL, and Madison WI units),
so the source is a full snapshot. Each row states its own compensation
("$12,941 to $14,289" maps to min/max, "up to $X" is a ceiling only) and
its study window ("Jul 19 2026 - Nov 16 2026" -> event_start/event_end).
Extra stipend sentences ride verbatim in ``quest.pay_note``; a figure we
cannot parse emits no salary keys and keeps the stated text there instead.
Rows carry no posted date, so none is invented (the DoC precedent: the
window is the event, never the post date). US site only; the en-gb
variant is never fetched.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://www.fortreaclinicaltrials.com"
_BROWSE_URL = _BASE + "/en-us/clinical-research/browse-studies"

_RANGE_RE = re.compile(
    r"^\$([\d,]+(?:\.\d+)?)\s*(?:to|[-–])\s*\$([\d,]+(?:\.\d+)?)\.?\s*"
)
_UP_TO_RE = re.compile(r"^up\s+to\s+\$([\d,]+(?:\.\d+)?)\.?\s*", re.IGNORECASE)
_SINGLE_RE = re.compile(r"^\$([\d,]+(?:\.\d+)?)\.?\s*")
_DATE_RANGE_RE = re.compile(
    r"^([A-Za-z]{3} \d{1,2} \d{4})\s*[-–]\s*([A-Za-z]{3} \d{1,2} \d{4})$"
)


def _cell_text(tr, class_name: str) -> str:
    node = tr.select_one(f"td.{class_name}")
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _parse_compensation(text: str) -> tuple[dict, str]:
    """The compensation cell to (salary fields, verbatim leftover note)."""
    text = re.sub(r"\s+", " ", text).strip()
    m = _RANGE_RE.match(text)
    if m:
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        fields = {
            "salary_min": lo,
            "salary_max": max(lo, hi),
            "salary_source": "reported",
        }
        return fields, text[m.end():].strip()
    m = _UP_TO_RE.match(text)
    if m:  # "up to $X" promises a ceiling, never a floor
        amount = float(m.group(1).replace(",", ""))
        return {"salary_max": amount, "salary_source": "reported"}, text[m.end():].strip()
    m = _SINGLE_RE.match(text)
    if m:
        amount = float(m.group(1).replace(",", ""))
        fields = {
            "salary_min": amount,
            "salary_max": amount,
            "salary_source": "reported",
        }
        return fields, text[m.end():].strip()
    return {}, text


def _normalize_row(tr) -> dict | None:
    """One browse-table row to a body-kind quest row, or None to skip."""
    title_cell = tr.select_one("td.views-field-title")
    link = title_cell.find("a") if title_cell else None
    if link is None or not link.get("href"):
        return None
    population = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
    if not population:
        return None
    # the protocol number sits as bare text after the anchor
    protocol = re.sub(
        r"\s+", " ",
        " ".join(s for s in title_cell.find_all(string=True, recursive=False)),
    ).strip()

    row: dict = {
        "title": f"{population} ({protocol})" if protocol else population,
        "company": "Fortrea",
        "location": _cell_text(tr, "views-field-field-location"),
        "url": urljoin(_BASE, link["href"]),
        "source": "fortrea",
        "vertical": "body",
        "description": _cell_text(tr, "views-field-field-study-design"),
    }

    dates = _DATE_RANGE_RE.match(_cell_text(tr, "views-field-field-dates-1"))
    if dates:
        try:
            row["event_start"] = datetime.strptime(dates.group(1), "%b %d %Y").date().isoformat()
            row["event_end"] = datetime.strptime(dates.group(2), "%b %d %Y").date().isoformat()
        except ValueError:
            row.pop("event_start", None)

    fields, note = _parse_compensation(_cell_text(tr, "views-field-field-compensation"))
    row.update(fields)

    quest: dict = {}
    if note:
        quest["pay_note"] = note
    if protocol:
        quest["protocol"] = protocol
    age = _cell_text(tr, "views-field-field-age-freetext")
    if age:
        quest["age"] = age
    smokers = _cell_text(tr, "views-field-field-smoker")
    if smokers:
        quest["smokers_allowed"] = smokers
    if quest:
        row["quest"] = quest
    return row


def _fetch_rows() -> list:
    try:
        resp = requests.get(
            _BROWSE_URL, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Fortrea browse fetch failed: %s", exc)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select("div.view-content table tbody tr")


@register_scraper(
    name="fortrea",
    display_name="Fortrea Clinical Trials",
    url="https://www.fortreaclinicaltrials.com",
    description="Phase-1 studies at Fortrea's own US research units with the stated study compensation",
    category="body",
    kind="body",
    # the browse table IS the entire current set; absence proves removal
    full_snapshot=True,
    # a handful of studies that turn over slowly; one polite fetch a day
    refresh_hours=24,
    allowed_url_hosts=("fortreaclinicaltrials.com",),
    enabled_by_default=False,
)
def search_fortrea(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch the current study set from Fortrea's US browse page.

    ``roles`` is ignored on purpose: studies are not career titles.
    """
    logger.info("Fetching studies from Fortrea Clinical Trials...")

    results: list[dict] = []
    seen_urls: set[str] = set()
    for tr in _fetch_rows():
        if len(results) >= max_results:
            break
        row = _normalize_row(tr)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("Fortrea: %d studies", len(results))
    return results
