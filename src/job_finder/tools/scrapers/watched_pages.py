"""Places I'd work at: part-time openings from careers pages the user watches.

Owner request, 2026-10-08: "why didnt this show up?
https://elorea.com/pages/barista-la". ELOREA posts its Koreatown barista
and scent advisor shifts only on its own Shopify careers page, never on
Indeed. The user pastes a page like that in Settings; every quest refresh
reads each one (robots.txt first, one request per host per second) and
puts the hourly or part-time openings near the saved place on the
Part-time lane, with the shop as the company and "Their site" as the
source.

How a page is read lives in _careers_page.py (hosted board hand-off,
JobPosting JSON-LD, known listing shapes). What stays is decided here:
in-person rows near the saved place (Los Angeles when none is saved)
that state part-time or hourly pay. Full-time salaried roles drop. Pay
shows only when the page states it. No LLM.

No host gate on the registry entry: rows point at whichever shop sites the
user watches. Every watched URL is http(s) (the API refuses anything else)
and row URLs are resolved against that page or come from an ATS fetcher.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from job_finder.tools.scrapers import _careers_page as pages
from job_finder.tools.scrapers._polite_fetch import FetchError, fetch_html
from job_finder.tools.scrapers._reddit import LA_LABEL, stated_place
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import publish_partial

logger = logging.getLogger(__name__)

SOURCE = "watched-pages"
DEFAULT_PLACE = LA_LABEL
RESULT_CEILING = 200
_DETAIL_LIMIT = 8
_WORKERS = 4
_TOTAL_BUDGET_S = 80.0

_ATS_FETCHERS: dict[str, tuple[str, str]] = {
    "greenhouse": ("greenhouse", "_fetch_company_jobs"),
    "lever": ("lever", "_fetch_company_postings"),
    "ashby": ("ashby", "_fetch_company_jobs"),
    "workable": ("workable", "_fetch_company_jobs"),
}

_SALARIED_TITLE_RE = re.compile(
    r"\b(?:director|head of|vice president|vp|chief|executive|general manager"
    r"|district manager|regional manager|salaried)\b",
    re.IGNORECASE,
)
_FULL_TIME_TITLE_RE = re.compile(r"\bfull[- ]?time\b", re.IGNORECASE)
_PART_TIME_TEXT_RE = re.compile(r"\bpart[- ]?time\b", re.IGNORECASE)
_HOURLY_TEXT_RE = re.compile(r"\bhourly\b|\bper hour\b|/\s*(?:hr|hour)\b", re.IGNORECASE)


def place_reachable(location: str, place: str | None) -> bool:
    """Whether a row's stated location is the saved place's metro."""
    target = stated_place(place or "") or stated_place(DEFAULT_PLACE)
    where = (location or "").strip()
    if not where:
        return True
    metro = stated_place(where)
    if metro == "Remote":
        return False
    if metro is not None:
        return metro == target
    city = (place or DEFAULT_PLACE).split(",")[0].strip().lower()
    return bool(city) and city in where.lower()


def _employment(row: dict) -> str:
    stated = pages.employment_type(row.get("employment"))
    if stated:
        return stated
    title = str(row.get("title") or "")
    if _PART_TIME_TEXT_RE.search(title):
        return "parttime"
    if _FULL_TIME_TITLE_RE.search(title):
        return "fulltime"
    if _PART_TIME_TEXT_RE.search(str(row.get("description") or "")):
        return "parttime"
    return ""


def keep_row(row: dict) -> bool:
    """Part-time or hourly, and not a salaried role."""
    if row.get("is_remote"):
        return False
    title = str(row.get("title") or "")
    period = str(row.get("salary_period") or "")
    if period == "yearly" or _SALARIED_TITLE_RE.search(title):
        return False
    employment = _employment(row)
    if employment == "fulltime" and period != "hourly":
        return False
    if employment == "parttime" or period == "hourly":
        return True
    return bool(_HOURLY_TEXT_RE.search(str(row.get("description") or "")))


def _ats_rows(ats: str, slug: str) -> list[dict]:
    module_name, fn_name = _ATS_FETCHERS[ats]
    module = importlib.import_module(f"job_finder.tools.scrapers.{module_name}")
    return getattr(module, fn_name)(slug, None, watchlist=True) or []


def _enrich(row: dict, fetch: Callable[[str], str]) -> None:
    """Fill a listing row's gaps from its own detail page's JobPosting."""
    try:
        detail = pages.jobposting_rows(fetch(row["url"]), row["url"])
    except FetchError:
        return
    if not detail:
        return
    match = next((d for d in detail if d["title"].lower() == row["title"].lower()), detail[0])
    for key in ("date_posted", "description", "salary_min", "salary_max",
                "salary_period", "salary_currency", "employment", "location"):
        if not row.get(key) and match.get(key):
            row[key] = match[key]


def to_quest_row(row: dict, shop: str) -> dict:
    out: dict = {
        "title": str(row.get("title") or "").strip(),
        "company": shop or str(row.get("company") or "").strip(),
        "location": str(row.get("location") or "").strip(),
        "is_remote": False,
        "url": str(row.get("url") or "").strip(),
        "source": SOURCE,
        "vertical": "parttime",
        "description": str(row.get("description") or ""),
    }
    if row.get("salary_min") is not None or row.get("salary_max") is not None:
        out["salary_min"] = row.get("salary_min")
        out["salary_max"] = row.get("salary_max")
        out["salary_period"] = str(row.get("salary_period") or "")
        out["salary_currency"] = str(row.get("salary_currency") or "USD")
        out["salary_source"] = "reported"
    posted = str(row.get("date_posted") or "").strip()
    if posted:
        out["date_posted"] = posted
    return out


STARTER_FILE = Path(__file__).parent / "data" / "watched_pages_starter.json"


def starter_list() -> list[dict]:
    """Suggested places ({name, url, area, hosting, note}) the user can add in one click.
    Never auto-added."""
    try:
        data = json.loads(STARTER_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("watched pages starter list unreadable", exc_info=True)
        return []
    return [
        {key: str(item.get(key) or "") for key in ("name", "url", "area", "hosting", "note")}
        for item in data
        if isinstance(item, dict) and item.get("url") and item.get("name")
    ]


def check_page(
    url: str,
    place: str | None = None,
    name: str = "",
    *,
    fetch: Callable[[str], str] = fetch_html,
    ats_fetch: Callable[[str, str], list[dict]] = _ats_rows,
) -> dict:
    """Read one watched page.

    Returns {name, found, rows, error, via}: ``found`` counts every opening
    the page lists, ``rows`` are the quest rows kept for the Part-time lane,
    ``error`` is a plain reason when the page could not be read.
    """
    result: dict = {"name": name, "found": 0, "rows": [], "error": "", "via": ""}
    board = pages.find_ats_board(url)
    html = ""
    if board is None:
        try:
            html = fetch(url)
        except FetchError as exc:
            result["error"] = str(exc)
            return result
        board = pages.find_ats_board(html)
    shop = name or (pages.shop_name(html, url) if html else "")
    result["name"] = shop

    if board:
        ats, slug = board
        result["via"] = ats
        try:
            raw = list(ats_fetch(ats, slug))
        except Exception as exc:
            logger.warning("watched page %s: %s board %s failed: %s", url, ats, slug, exc)
            result["error"] = "Could not read the job board that page links to."
            return result
        if not shop:
            shop = next((str(r.get("company") or "") for r in raw if r.get("company")), slug)
            result["name"] = shop
    else:
        raw = pages.jobposting_rows(html, url)
        result["via"] = "jobposting" if raw else "listing"
        if not raw:
            raw = pages.listing_rows(html, url)
    result["found"] = len(raw)

    host = (urlsplit(url).hostname or "").lower()
    nearby = [r for r in raw if place_reachable(str(r.get("location") or ""), place)]
    if result["via"] == "listing":
        candidates = [
            r for r in nearby
            if not (_employment(r) == "fulltime" and r.get("salary_period") != "hourly")
        ]
        for row in candidates[:_DETAIL_LIMIT]:
            if (urlsplit(row["url"]).hostname or "").lower() == host and row["url"] != url:
                _enrich(row, fetch)
    result["rows"] = [to_quest_row(r, shop) for r in nearby if keep_row(r)]
    return result


@register_scraper(
    name=SOURCE,
    display_name="Their site",
    url="",
    description="Part-time openings from careers pages you watch in Settings",
    category="direct",
    kind="parttime",
    enabled_by_default=False,
    stale_after_days=10,
    refresh_hours=24,
    result_ceiling=RESULT_CEILING,
)
def search_watched_pages(
    roles: list[str] | None = None,
    max_results: int = RESULT_CEILING,
    place: str | None = None,
    partial_sink: list[dict] | None = None,
    **kwargs,
) -> list[dict]:
    """Every watched page, read once. ``roles`` is ignored: the user chose
    these shops, and the keep rule is part-time or hourly."""
    from job_finder.models.watched_pages import load_watched_pages, record_checks

    watched = load_watched_pages()
    if not watched:
        return []
    started = time.monotonic()

    def _one(page: dict) -> tuple[dict, dict]:
        if time.monotonic() - started > _TOTAL_BUDGET_S:
            return page, {"found": 0, "rows": [], "error": "", "skipped": True}
        checked = check_page(page["url"], place, page.get("name") or "")
        publish_partial(partial_sink, checked["rows"])
        return page, checked

    with ThreadPoolExecutor(max_workers=min(_WORKERS, len(watched))) as pool:
        outcomes = list(pool.map(_one, watched))

    results: list[dict] = []
    seen: set[str] = set()
    stamps: list[dict] = []
    for page, checked in outcomes:
        if checked.get("skipped"):
            continue
        stamps.append({"url": page["url"], "found": len(checked["rows"]),
                       "error": checked["error"]})
        for row in checked["rows"]:
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            results.append(row)
    record_checks(stamps)
    logger.info("watched-pages: %d rows from %d pages", len(results), len(watched))
    return results[:max_results]
