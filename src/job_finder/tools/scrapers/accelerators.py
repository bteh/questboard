"""Accelerator majors (pitch kind): curated application windows, three pages, one scraper.

Live-probed 2026-07-12. This is a curated set, not a crawl: the three major
accelerators publish their current application window on one page each, and
one weekly fetch of those three pages IS the whole set (full_snapshot).

1. Y Combinator, ``GET https://www.ycombinator.com/apply`` (robots allows
   /apply). The React root div carries a ``data-page`` attribute with
   HTML-escaped JSON: ``rails_context.applyBatchLong`` ("Fall 2026"),
   ``rails_context.applyDeadlineShort`` ("July 27"), and
   ``props.apply_url``. One row per fetch; the deadline has no year, so it
   rolls forward to the next occurrence from today.
2. Techstars, ``GET https://www.techstars.com/accelerators`` (robots
   Allow: /). ``__NEXT_DATA__`` ``props.pageProps.programs`` lists ~21
   programs with ``programStatus`` and per-term ``importantDates``. Only
   programs whose status says "Now Reviewing Applications" emit, the ISO
   ``final_deadline`` becomes ``quest.apply_by``, and a past deadline drops
   the row even when the status string lingers.
3. 500 Global, ``GET https://500.co/founders/flagship``. Prose only:
   "Applications close October 11th for Flagship Accelerator Batch 36."
   Parsed with ONE strict regex; if the sentence does not match that exact
   grammar, 500 emits NO row. Never guess a deadline from loose prose.

Honesty notes: no salary keys ever (funding terms vary per program); if a
page someday states a check size verbatim inside a region we already parse,
it may ride in ``quest.pay_note`` only. ``company`` is the accelerator
itself, the real counterparty you pitch. No entry fees anywhere in this set
(probe verdict). Each page degrades independently: one page failing must
not kill the other two.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from html import unescape

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_SOURCE = "accelerators"

_YC_URL = "https://www.ycombinator.com/apply"
_TECHSTARS_URL = "https://www.techstars.com/accelerators"
_TECHSTARS_APPLY_URL = "https://apply.techstars.com?accelerator={slug}"
_FIVEHUNDRED_URL = "https://500.co/founders/flagship"

_TECHSTARS_OPEN_STATUS = "Now Reviewing Applications"

_DATA_PAGE_RE = re.compile(r'data-page="([^"]*)"')
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"[^>]*>(.+?)</script>', re.DOTALL
)
_MONTH_DAY_RE = re.compile(r"^([A-Z][a-z]+)\s+(\d{1,2})$")
# The one strict grammar for 500 Global; anything else means no row.
_FLAGSHIP_RE = re.compile(
    r"Applications close ([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th)?"
    r" for Flagship Accelerator Batch (\d+)\."
)

_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def _today() -> date:
    """Wrapped so tests can freeze the clock."""
    return datetime.now(timezone.utc).date()


def _fetch(url: str) -> str:
    resp = requests.get(
        url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.text


def _next_occurrence(month_name: str, day: int) -> str | None:
    """The next ISO date for a year-less "Month D"; None when it isn't a date."""
    month = _MONTHS.get(month_name)
    if not month:
        return None
    today = _today()
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate.isoformat()
    return None


def _parse_month_day(text: str) -> str | None:
    m = _MONTH_DAY_RE.match(str(text or "").strip())
    if not m:
        return None
    return _next_occurrence(m.group(1), int(m.group(2)))


def _yc_rows() -> list[dict]:
    """One row for the current YC batch, [] on anything unexpected."""
    try:
        html_text = _fetch(_YC_URL)
    except Exception as exc:
        logger.warning("accelerators: YC fetch failed: %s", exc)
        return []
    m = _DATA_PAGE_RE.search(html_text)
    if not m:
        return []
    try:
        data = json.loads(unescape(m.group(1)))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("accelerators: YC data-page unparseable: %s", exc)
        return []
    if not isinstance(data, dict):
        return []
    props = data.get("props") if isinstance(data.get("props"), dict) else {}
    rails = (
        data.get("rails_context")
        if isinstance(data.get("rails_context"), dict) else {}
    )
    batch = str(rails.get("applyBatchLong") or props.get("batch_name_long") or "").strip()
    deadline_short = str(
        rails.get("applyDeadlineShort") or props.get("deadline") or ""
    ).strip()
    apply_url = str(props.get("apply_url") or "").strip()
    if not batch or not apply_url:
        return []
    row: dict = {
        "title": f"Y Combinator {batch} batch",
        "company": "Y Combinator",
        "url": apply_url,
        "source": _SOURCE,
        "vertical": "pitch",
        "description": f"Apply to the Y Combinator {batch} batch.",
    }
    apply_by = _parse_month_day(deadline_short)
    if apply_by:
        row["quest"] = {"apply_by": apply_by}
    return [row]


def _term_dates(program: dict) -> tuple[str | None, str | None]:
    """(final_deadline, applications_open_date), latest across terms."""
    deadlines: list[str] = []
    opens: list[str] = []
    for term in program.get("acceleratorTerms") or []:
        if not isinstance(term, dict):
            continue
        for entry in term.get("importantDates") or []:
            if not isinstance(entry, dict):
                continue
            key = entry.get("dateDescriptionKey")
            value = str(entry.get("date") or "").strip()
            if not value:
                continue
            if key == "final_deadline":
                deadlines.append(value)
            elif key == "applications_open_date":
                opens.append(value)
    return (max(deadlines) if deadlines else None, max(opens) if opens else None)


def _iso_date_or_none(raw: str | None) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _techstars_rows() -> list[dict]:
    """One row per Techstars program that is open AND not past its deadline."""
    try:
        html_text = _fetch(_TECHSTARS_URL)
    except Exception as exc:
        logger.warning("accelerators: Techstars fetch failed: %s", exc)
        return []
    m = _NEXT_DATA_RE.search(html_text)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("accelerators: Techstars __NEXT_DATA__ unparseable: %s", exc)
        return []
    if not isinstance(data, dict):
        return []
    programs = (
        data.get("props", {}).get("pageProps", {}).get("programs")
        if isinstance(data.get("props"), dict) else None
    )
    if not isinstance(programs, list):
        return []

    today = _today()
    rows: list[dict] = []
    for program in programs:
        if not isinstance(program, dict):
            continue
        statuses = program.get("programStatus")
        if not isinstance(statuses, list):
            statuses = [statuses]
        if _TECHSTARS_OPEN_STATUS not in [str(s) for s in statuses]:
            continue
        name = str(program.get("name") or "").strip()
        slug = str(program.get("slug") or "").strip()
        if not name or not slug:
            continue
        deadline_raw, opened_raw = _term_dates(program)
        deadline = _iso_date_or_none(deadline_raw)
        # the status string lingers after the window closes (seen live);
        # a stated past deadline wins over the label
        if deadline is not None and deadline < today:
            continue
        row: dict = {
            "title": name,
            "company": "Techstars",
            "url": _TECHSTARS_APPLY_URL.format(slug=slug),
            "source": _SOURCE,
            "vertical": "pitch",
            "description": f"{name}. Status: {_TECHSTARS_OPEN_STATUS}.",
        }
        region = str(program.get("programRegion") or "").strip()
        if region:
            row["location"] = region
        opened = _iso_date_or_none(opened_raw)
        if opened is not None and opened <= today:
            row["date_posted"] = opened.isoformat()
        if deadline is not None:
            row["quest"] = {"apply_by": deadline.isoformat()}
        rows.append(row)
    return rows


def _fivehundred_rows() -> list[dict]:
    """One row when the flagship sentence matches the strict grammar, else []."""
    try:
        html_text = _fetch(_FIVEHUNDRED_URL)
    except Exception as exc:
        logger.warning("accelerators: 500 Global fetch failed: %s", exc)
        return []
    m = _FLAGSHIP_RE.search(html_text)
    if not m:
        logger.info("accelerators: 500 Global sentence did not match, skipping")
        return []
    apply_by = _next_occurrence(m.group(1), int(m.group(2)))
    if not apply_by:
        return []
    batch = m.group(3)
    return [{
        "title": f"500 Global Flagship Accelerator Batch {batch}",
        "company": "500 Global",
        "url": _FIVEHUNDRED_URL,
        "source": _SOURCE,
        "vertical": "pitch",
        "description": m.group(0),
        "quest": {"apply_by": apply_by},
    }]


@register_scraper(
    name="accelerators",
    display_name="Accelerator majors",
    url="https://www.ycombinator.com/apply",
    description="Open application windows at Y Combinator, Techstars, and 500 Global with real deadlines",
    category="pitch",
    kind="pitch",
    # three curated pages ARE the whole set; absence across runs proves closure
    full_snapshot=True,
    # application windows move on a batch rhythm; weekly is plenty
    refresh_hours=168,
    allowed_url_hosts=("ycombinator.com", "techstars.com", "500.co"),
    enabled_by_default=False,
)
def search_accelerators(
    roles: list[str] | None = None,
    max_results: int = 25,
    **kwargs,
) -> list[dict]:
    """Fetch open accelerator application windows from the three curated pages.

    ``roles`` is ignored on purpose: pitches are not career titles.
    """
    logger.info("Fetching accelerator application windows (3 curated pages)...")
    rows: list[dict] = []
    for sub_source in (_yc_rows, _techstars_rows, _fivehundred_rows):
        if len(rows) >= max_results:
            break
        try:
            rows.extend(sub_source())
        except Exception as exc:
            logger.warning(
                "accelerators: %s failed (non-fatal): %s", sub_source.__name__, exc
            )
    rows = rows[:max_results]
    logger.info("Accelerator majors: %d open windows", len(rows))
    return rows
