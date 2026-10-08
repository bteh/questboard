"""EdJoin: California school district, county office, and college jobs.

EdJoin is the statewide job board run by the San Joaquin County Office of
Education; most California school districts (Pasadena USD, El Monte City SD,
Brea Olinda USD, Fullerton SD, LACOE, OCDE...) and several community college
districts post their classified IT, data, and business roles here with the
pay box filled in. robots.txt allows everything, the site states no
automation ban, and its own search page reads the JSON endpoint used here
(/Home/LoadJobs).

Keyword search matches every word against the title, so a full role like
"IT Support Specialist" misses "Technology Support Specialist". Each role is
searched as written and by its last word; the shared role filter decides.
"""

from __future__ import annotations

import logging
import re

from job_finder.tools.scrapers._public_sector import (
    is_internal_only,
    job_type_from,
    money_amounts,
    period_from_words,
    wants_california,
)
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _get_json,
    _match_roles,
    date_confidence_for,
    normalize_posted_date,
    publish_partial,
    rank_by_relevance,
)
from job_finder.us_states import STATE_TO_ABBR

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.edjoin.org/Home/LoadJobs"
POSTING_URL = "https://www.edjoin.org/Home/JobPosting/{posting_id}"
_ROWS_PER_PAGE = 100
_MAX_PAGES = 3
_MAX_ROLES = 8
_TIMEOUT = 20
_EPOCH_RE = re.compile(r"-?\d{9,13}")
_WORD_RE = re.compile(r"[A-Za-z]+")


def search_terms(roles: list[str] | None) -> list[str]:
    """The keyword queries for these roles: each role, then each last word."""
    terms: list[str] = []
    for role in (roles or [])[:_MAX_ROLES]:
        role = " ".join(role.split())
        if role and role.lower() not in (t.lower() for t in terms):
            terms.append(role)
    for role in list(terms):
        words = _WORD_RE.findall(role)
        if len(words) > 1:
            head = words[-1].lower()
            if head not in (t.lower() for t in terms):
                terms.append(head)
    return terms


def _params(keywords: str, page: int) -> dict:
    return {
        "rows": _ROWS_PER_PAGE, "page": page, "sort": "postingDate", "sortVal": 0,
        "order": "desc", "keywords": keywords, "location": "", "searchType": "all",
        "regions": "", "jobTypes": "", "days": 0, "empType": "", "catID": 0,
        "onlineApps": "", "recruitmentCenterID": 0, "stateID": 0, "regionID": 0,
        "districtID": 0, "searchID": 0,
    }


def _epoch(raw: object) -> str:
    m = _EPOCH_RE.search(str(raw or ""))
    if not m or m.group(0).startswith("-"):
        return ""
    return m.group(0)


def _location(posting: dict) -> str:
    city = " ".join(str(posting.get("city") or "").split())
    state_name = str(posting.get("stateName") or "").strip()
    state = STATE_TO_ABBR.get(state_name.lower(), state_name)
    if city and state:
        return f"{city}, {state}"
    return city or state


def stated_pay(posting: dict) -> tuple[float | None, float | None, str | None]:
    """(min, max, period) from EdJoin's structured pay box, only as stated."""
    choice = str(posting.get("SalaryInfoSelect") or "").lower()
    if "range" in choice:
        lows = money_amounts(posting.get("PayRangeFrom"))
        highs = money_amounts(posting.get("PayRangeTo"))
        period = period_from_words(posting.get("PayRangeDropdown"))
        low = lows[-1] if lows else None
        high = highs[-1] if highs else None
    elif "single" in choice:
        amounts = money_amounts(posting.get("SingleRate"))
        period = period_from_words(posting.get("SingleRateDropdown"))
        low = amounts[0] if amounts else None
        high = amounts[-1] if amounts else None
    else:
        return None, None, None
    if period is None or (low is None and high is None):
        return None, None, None
    if low is not None and high is not None and high < low:
        return None, None, None
    return low, high, period


def to_row(posting: dict) -> dict | None:
    """One EdJoin search result to a career row, or None when unusable."""
    title = " ".join(str(posting.get("positionTitle") or "").split())
    posting_id = posting.get("postingID")
    if not title or not posting_id:
        return None
    employer = " ".join(str(posting.get("districtName") or "").split())
    job_type_label = str(posting.get("jobType") or "").strip()
    time_basis = str(posting.get("FullTimePartTime") or "").strip()
    salary_info = " ".join(str(posting.get("salaryInfo") or "").split())
    description = ". ".join(p for p in (job_type_label, time_basis, salary_info) if p)
    posted = _epoch(posting.get("postingDate"))

    row: dict = {
        "title": title,
        "company": employer,
        "location": _location(posting),
        "url": POSTING_URL.format(posting_id=posting_id),
        "source": "edjoin",
        "description": description,
        "salary_min": None,
        "salary_max": None,
        "date_posted": normalize_posted_date(posted) if posted else "",
        "date_confidence": date_confidence_for(posted) if posted else "missing",
        "is_remote": False,
        "company_size": "",
        "job_type": job_type_from(time_basis),
    }
    low, high, period = stated_pay(posting)
    if period:
        row["salary_min"], row["salary_max"] = low, high
        row["salary_period"] = period
        row["salary_currency"] = "USD"
    return row


def parse_results(
    payload: dict | None,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> list[dict]:
    """Role-matched, open-to-the-public rows from one LoadJobs response."""
    if not isinstance(payload, dict):
        return []
    rows: list[dict] = []
    for posting in payload.get("data") or []:
        if not isinstance(posting, dict):
            continue
        row = to_row(posting)
        if row is None or is_internal_only(row["title"]):
            continue
        if roles and not _match_roles(
            row["title"], roles, match_mode=match_mode, include_founding=include_founding,
        ):
            continue
        rows.append(row)
    return rows


@register_scraper(
    name="edjoin",
    display_name="EdJoin",
    url="https://www.edjoin.org",
    description="California school district, county office, and college jobs with stated pay",
    category="public",
    kind="career",
    allowed_url_hosts=("edjoin.org",),
)
def search_edjoin(
    roles: list[str] | None = None,
    max_results: int = 100,
    locations: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    partial_sink = kwargs.get("partial_sink")
    if not roles:
        return []
    if not wants_california(locations):
        logger.info("EdJoin: no California place saved; skipping")
        return []

    by_id: dict[str, dict] = {}
    for term in search_terms(roles):
        for page in range(1, _MAX_PAGES + 1):
            payload = _get_json(SEARCH_URL, params=_params(term, page), timeout=_TIMEOUT)
            if not isinstance(payload, dict):
                break
            fresh = [
                row for row in parse_results(
                    payload, roles, match_mode=match_mode, include_founding=include_founding,
                )
                if row["url"] not in by_id
            ]
            for row in fresh:
                by_id[row["url"]] = row
            publish_partial(partial_sink, fresh)
            if page >= int(payload.get("totalPages") or 0):
                break

    rows = list(by_id.values())
    logger.info("EdJoin: %d role-matched postings", len(rows))
    return rank_by_relevance(rows, roles)[:max_results]
