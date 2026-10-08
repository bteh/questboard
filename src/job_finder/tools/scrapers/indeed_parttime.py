"""Part-time shifts near the user's saved place (parttime kind) via JobSpy Indeed.

Owner request, 2026-10-08: barista, cafe, boba, restaurant, retail, and
event shifts near home (Koreatown LA was the example). Reuses the career
path's JobSpy wrapper, Indeed only, with Indeed's own part-time filter and
a tight radius around the saved place. Indeed ignores the part-time filter
when a posted-within window is set, so the window is applied here on
date_posted instead. No saved place means no fetch: a
nationwide part-time firehose is not "near you".

A row stays only when it reads as an hourly shift: Indeed's job type is
not full-time alone, the title doesn't say full-time or name a salaried
manager role, and any stated pay isn't yearly. Pay shows only when Indeed
states an amount.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _parse_posted_date, publish_partial

logger = logging.getLogger(__name__)

SOURCE = "indeed-parttime"

SEARCH_TERMS: tuple[str, ...] = (
    "barista",
    "coffee",
    "cafe",
    "boba",
    "server",
    "host",
    "retail associate",
    "cashier",
    "event staff",
)

DISTANCE_MILES = 10
_DEFAULT_MAX_DAYS = 14
# Live probe near Koreatown, Oct 8 2026: barista 90, coffee 84 part-time
# posts within 10 miles, each term answering in 10-20s.
_PER_TERM = 100
RESULT_CEILING = 500
_WORKERS = 3
_TERM_TIMEOUT_S = 30.0
# run_scrapers stops waiting at 100s: no new term starts after 80s, and no
# term may run past 95s
_TOTAL_BUDGET_S = 80.0
_HARD_STOP_S = 95.0

_FULL_TIME_TITLE_RE = re.compile(r"\bfull[- ]?time\b", re.IGNORECASE)
_PART_TIME_TITLE_RE = re.compile(r"\bpart[- ]?time\b", re.IGNORECASE)
_SALARIED_TITLE_RE = re.compile(
    r"\b(?:manager|director|supervisor|executive chef|sous chef|chef de cuisine"
    r"|district|regional|salaried)\b",
    re.IGNORECASE,
)
_REMOTE_PLACES = {"", "remote", "anywhere", "online", "us", "usa", "united states"}


def _job_types(raw: str) -> set[str]:
    return {part.strip().lower() for part in (raw or "").split(",") if part.strip()}


def keep_row(row: dict) -> bool:
    """Whether one search_jobs row reads as a part-time hourly shift."""
    title = str(row.get("title") or "").strip()
    if not title or not row.get("url"):
        return False
    if row.get("is_remote"):
        return False
    types = _job_types(str(row.get("job_type") or ""))
    if "fulltime" in types and "parttime" not in types:
        return False
    if _FULL_TIME_TITLE_RE.search(title) and not _PART_TIME_TITLE_RE.search(title):
        return False
    if _SALARIED_TITLE_RE.search(title):
        return False
    if str(row.get("salary_period") or "").lower() == "yearly":
        return False
    return True


def to_quest_row(row: dict) -> dict:
    """Map a kept search_jobs row onto the quest row shape."""
    out: dict = {
        "title": str(row.get("title") or "").strip(),
        "company": str(row.get("company") or "").strip(),
        "location": str(row.get("location") or "").strip(),
        "is_remote": False,
        "url": str(row.get("url") or "").strip(),
        "source": SOURCE,
        "vertical": "parttime",
        "description": str(row.get("description") or ""),
    }
    lo, hi = row.get("salary_min"), row.get("salary_max")
    if lo is not None or hi is not None:
        out["salary_min"] = lo
        out["salary_max"] = hi
        out["salary_period"] = str(row.get("salary_period") or "")
        out["salary_currency"] = str(row.get("salary_currency") or "USD")
        out["salary_source"] = "reported"
    posted = str(row.get("date_posted") or "").strip()
    if posted:
        out["date_posted"] = posted
    return out


def _too_old(row: dict, cutoff: datetime) -> bool:
    posted = _parse_posted_date(row.get("date_posted"))
    if posted is None:
        return False
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return posted < cutoff


def filter_rows(
    rows: list[dict],
    max_results: int,
    max_days_old: int = _DEFAULT_MAX_DAYS,
    now: datetime | None = None,
) -> list[dict]:
    """Keep recent part-time shifts, drop repeats across search terms."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_days_old)
    results: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if len(results) >= max_results:
            break
        if not keep_row(row) or _too_old(row, cutoff):
            continue
        quest = to_quest_row(row)
        key = "|".join(
            (quest["company"].lower(), quest["title"].lower(), quest["location"].lower())
        )
        if quest["url"] in seen or key in seen:
            continue
        seen.update((quest["url"], key))
        results.append(quest)
    return results


@register_scraper(
    name=SOURCE,
    display_name="Indeed",
    url="https://www.indeed.com",
    description="Part-time cafe, restaurant, retail, and event shifts within 10 miles of your place",
    category="jobspy",
    kind="parttime",
    enabled_by_default=False,
    stale_after_days=10,
    refresh_hours=12,
    allowed_url_hosts=("indeed.com",),
    result_ceiling=RESULT_CEILING,
)
def search_indeed_parttime(
    roles: list[str] | None = None,
    max_results: int = RESULT_CEILING,
    max_days_old: int | None = None,
    place: str | None = None,
    partial_sink: list[dict] | None = None,
    **kwargs,
) -> list[dict]:
    """Search Indeed for part-time shifts near ``place``. ``roles`` is
    ignored: the term list is fixed to hourly shift work."""
    where = (place or "").strip()
    if where.lower() in _REMOTE_PLACES:
        logger.info("indeed-parttime: no saved place, skipped")
        return []

    from job_finder.tools.job_search_tool import search_jobs

    days = max_days_old or _DEFAULT_MAX_DAYS
    started = time.monotonic()

    def _fetch(term: str) -> list[dict]:
        elapsed = time.monotonic() - started
        if elapsed > _TOTAL_BUDGET_S:
            logger.info("indeed-parttime: time budget spent before %r", term)
            return []
        rows = search_jobs(
            search_term=term,
            location=where,
            results_wanted=_PER_TERM,
            hours_old=None,
            boards=["indeed"],
            distance=DISTANCE_MILES,
            job_type="parttime",
            scrape_timeout=max(1.0, min(_TERM_TIMEOUT_S, _HARD_STOP_S - elapsed)),
        )
        publish_partial(partial_sink, filter_rows(rows, max_results, days))
        return rows

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        per_term = list(pool.map(_fetch, SEARCH_TERMS))

    raw = [row for rows in per_term for row in rows]
    results = filter_rows(raw, max_results, days)
    logger.info("indeed-parttime: %d of %d rows kept near %s", len(results), len(raw), where)
    return results
