"""Hosted job boards a watched page can be, read through the board's own API.

Shops near the owner's brother's search (San Gabriel Valley, North Orange
County) and LA cafes post on boards the company-watchlist scrapers never
covered. Researched and probed live 2026-10-08, one reader per board:

- Rippling (Alfred): api.rippling.com/platform/api/ats/v1/board/<slug>/jobs,
  then one detail GET per nearby opening for job type and pay.
- Workday (Uniqlo, fastretailing / retail_us_Uniqlo): the CXS search,
  paged with no search text, then a detail GET per nearby opening.
- ADP Workforce Now (Verve Coffee): the public job-requisitions JSON for
  the board's cid. Pay type and range come in the list.
- Paylocity (Bluestone Lane): the board page's window.pageData job list,
  then each nearby opening's detail page, which carries JobPosting JSON-LD.

Not here, on purpose: UKG Pro (H Mart, Daiso). recruiting.ultipro.com's
robots.txt says "Disallow: /" for every agent and disallows */JobBoardView,
the search API's path.

Every request goes through _polite_fetch (robots.txt, host pacing); the
fetchers are parameters so tests replay captured responses. Rows use the
_careers_page row shape; watched_pages decides which to keep.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote

from job_finder.tools.scrapers import _careers_page as pages
from job_finder.tools.scrapers._polite_fetch import FetchError, fetch_html, fetch_json

logger = logging.getLogger(__name__)

DETAIL_CAP = 25
WORKDAY_PAGE = 20
WORKDAY_MAX_ROWS = 400
ADP_PAGE = 20
ADP_MAX_ROWS = 200
ADP_DEFAULT_CCID = "19000101_000001"

Near = Callable[[str], bool]


@dataclass(frozen=True)
class Board:
    kind: str
    ref: dict = field(default_factory=dict)


_RIPPLING_RE = re.compile(
    r"(?:ats\.rippling\.com/|api\.rippling\.com/platform/api/ats/v1/board/)([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_WORKDAY_RE = re.compile(
    r"https?://[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>]+", re.IGNORECASE,
)
_ADP_RE = re.compile(
    r"workforcenow\.adp\.com/[^\s\"'<>]*?[?&](?:amp;)?cid=([0-9a-f-]{36})"
    r"(?:[^\s\"'<>]*?[?&](?:amp;)?ccId=([0-9_]+))?",
    re.IGNORECASE,
)
_PAYLOCITY_RE = re.compile(
    r"recruiting\.paylocity\.com/recruiting/jobs/All/([0-9a-f-]{36})", re.IGNORECASE,
)
_RIPPLING_NOT_SLUGS = {"platform", "internal", "api"}


def find_board(text: str) -> Board | None:
    """The hosted board a URL is, or the first one an HTML page links."""
    text = text or ""
    match = _RIPPLING_RE.search(text)
    if match and match.group(1).lower() not in _RIPPLING_NOT_SLUGS:
        return Board("rippling", {"slug": match.group(1).lower()})
    for match in _WORKDAY_RE.finditer(text):
        from job_finder.tools.scrapers.workday import _employer_from_url

        employer = _employer_from_url(match.group(0).replace("&amp;", "&"))
        if employer:
            return Board("workday", employer)
    match = _ADP_RE.search(text)
    if match:
        return Board("adp", {"cid": match.group(1).lower(),
                             "ccid": match.group(2) or ADP_DEFAULT_CCID})
    match = _PAYLOCITY_RE.search(text)
    if match:
        return Board("paylocity", {"guid": match.group(1).lower()})
    return None


def _text(html: str) -> str:
    return pages._plain_text(html)


def _row(title: str, location: str, url: str, **extra) -> dict:
    row = {
        "title": " ".join(str(title or "").split()),
        "company": "",
        "location": location,
        "url": url,
        "employment": "",
        "description": "",
        "is_remote": False,
    }
    row.update(extra)
    return row


# --- Rippling ----------------------------------------------------------------

_RIPPLING_API = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
_RIPPLING_FREQ = {"HOUR": "hourly", "YEAR": "yearly", "MONTH": "monthly", "WEEK": "weekly"}


def _rippling_detail(row: dict, detail: dict) -> None:
    """Alfred, Oct 8 2026: employmentType.label is HOURLY_PT, HOURLY_FT, or
    SALARIED_FT; payRangeDetails is usually empty and the wage sits in the
    role text ("Wage: $18.67/hr + tips")."""
    label = str((detail.get("employmentType") or {}).get("label") or "").upper()
    row["employment"] = "parttime" if label.endswith("_PT") else (
        "fulltime" if label.endswith("_FT") else "")
    description = detail.get("description") or {}
    role = description.get("role") if isinstance(description, dict) else description
    row["description"] = _text(str(role or ""))
    row["company"] = str(detail.get("companyName") or "")
    posted = str(detail.get("createdOn") or "")[:10]
    if posted:
        row["date_posted"] = posted
    ranges = detail.get("payRangeDetails") or []
    pay = None
    if ranges and isinstance(ranges[0], dict) and ranges[0].get("rangeStart") is not None:
        first = ranges[0]
        pay = {
            "salary_min": float(first["rangeStart"]),
            "salary_max": float(first.get("rangeEnd") or first["rangeStart"]),
            "salary_period": _RIPPLING_FREQ.get(str(first.get("frequency") or "").upper(), ""),
            "salary_currency": str(first.get("currency") or "USD"),
        }
    pay = pay or pages.parse_pay_text(row["description"])
    if pay:
        row.update(pay)
    if not row.get("salary_period"):
        if label.startswith("HOURLY"):
            row["salary_period"] = "hourly"
        elif label.startswith("SALARIED"):
            row["salary_period"] = "yearly"


def read_rippling(slug: str, near: Near, fetch: Callable = fetch_json) -> tuple[int, list[dict]]:
    base = _RIPPLING_API.format(slug=quote(slug))
    listing = fetch(base)
    if not isinstance(listing, list):
        return 0, []
    rows: list[dict] = []
    for item in listing:
        place = (item.get("workLocation") or {}).get("label") or ""
        if not item.get("uuid") or not near(str(place)):
            continue
        row = _row(item.get("name"), str(place), str(item.get("url") or ""))
        if len(rows) < DETAIL_CAP:
            try:
                _rippling_detail(row, fetch(f"{base}/{item['uuid']}") or {})
            except FetchError as exc:
                logger.info("rippling %s detail %s: %s", slug, item["uuid"], exc)
        rows.append(row)
    return len(listing), rows


# --- Workday -----------------------------------------------------------------


def _workday_detail(row: dict, info: dict) -> None:
    """Uniqlo, Oct 8 2026: timeType "Part time" / "Full time", the pay is
    the description's first line ("Salary: $18.50 / hour")."""
    row["employment"] = pages.employment_type(info.get("timeType"))
    row["description"] = _text(str(info.get("jobDescription") or ""))[:5000]
    row["location"] = str(info.get("location") or row["location"])
    posted = str(info.get("startDate") or "")[:10]
    if posted:
        row["date_posted"] = posted
    row["is_remote"] = bool(info.get("remoteType"))
    pay = pages.parse_pay_text(row["description"])
    if pay:
        row.update(pay)


def read_workday(employer: dict, near: Near, fetch: Callable = fetch_json) -> tuple[int, list[dict]]:
    api = f"{employer['base_url']}/wday/cxs/{employer['tenant']}/{employer['site_id']}"
    postings: list[dict] = []
    total = None
    offset = 0
    while offset < WORKDAY_MAX_ROWS and (total is None or offset < total):
        body = {"appliedFacets": {}, "limit": WORKDAY_PAGE, "offset": offset, "searchText": ""}
        try:
            page = fetch(f"{api}/jobs", body)
        except FetchError:
            if total is None:
                raise
            logger.info("workday %s: stopped paging at %d", employer["tenant"], offset)
            break
        batch = page.get("jobPostings") or []
        if total is None:
            total = int(page.get("total") or 0)
        if not batch:
            break
        postings.extend(batch)
        offset += WORKDAY_PAGE
    rows: list[dict] = []
    for item in postings:
        path = str(item.get("externalPath") or "")
        place = str(item.get("locationsText") or "")
        if not path or not near(place):
            continue
        row = _row(item.get("title"), place,
                   f"{employer['base_url']}/{employer['site_id']}{path}")
        if len(rows) < DETAIL_CAP:
            try:
                detail = fetch(f"{api}{path}") or {}
                _workday_detail(row, detail.get("jobPostingInfo") or {})
            except FetchError as exc:
                logger.info("workday %s detail %s: %s", employer["tenant"], path, exc)
        rows.append(row)
    return len(postings), rows


# --- ADP Workforce Now -------------------------------------------------------

_ADP_API = (
    "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/"
    "job-requisitions?cid={cid}&lang=en_US&locale=en_US&$top={top}&$skip={skip}"
)
_ADP_JOB = (
    "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
    "?cid={cid}&ccId={ccid}&jobId={job}&lang=en_US"
)
_ADP_PERIOD = {"hourly": "hourly", "annually": "yearly", "monthly": "monthly",
               "weekly": "weekly", "daily": "daily"}


def _adp_row(item: dict, board: dict) -> dict:
    """Verve Coffee, Oct 8 2026: SalaryType "Hourly" or "Annually" in
    customFieldGroup.codeFields; minimumRate 0.0 means only a top is stated."""
    seen: list[str] = []
    for loc in item.get("requisitionLocations") or []:
        address = loc.get("address") or {}
        city = str(address.get("cityName") or "").strip()
        state = str((address.get("countrySubdivisionLevel1") or {}).get("codeValue") or "")
        place = ", ".join(p for p in (city, state) if p)
        if place and place not in seen:
            seen.append(place)
    job = str(item.get("itemID") or "").split("_")[0]
    row = _row(item.get("requisitionTitle"), "; ".join(seen),
               _ADP_JOB.format(cid=board["cid"], ccid=board["ccid"], job=job))
    posted = str(item.get("postDate") or "")[:10]
    if posted:
        row["date_posted"] = posted
    codes = {
        str((c.get("nameCode") or {}).get("codeValue") or ""): str(c.get("shortName") or "")
        for c in (item.get("customFieldGroup") or {}).get("codeFields") or []
    }
    period = _ADP_PERIOD.get(codes.get("SalaryType", "").lower(), "")
    pay = item.get("payGradeRange") or {}
    lo = (pay.get("minimumRate") or {}).get("amountValue")
    hi = (pay.get("maximumRate") or {}).get("amountValue")
    if hi:
        row.update({
            "salary_min": float(lo) if lo else float(hi),
            "salary_max": float(hi),
            "salary_period": period,
            "salary_currency": str((pay.get("maximumRate") or {}).get("currencyCode") or "USD"),
        })
    elif period:
        row["salary_period"] = period
    return row


def read_adp(board: dict, near: Near, fetch: Callable = fetch_json) -> tuple[int, list[dict]]:
    items: list[dict] = []
    total = None
    while len(items) < ADP_MAX_ROWS and (total is None or len(items) < total):
        url = _ADP_API.format(cid=board["cid"], top=ADP_PAGE, skip=len(items))
        try:
            page = fetch(url)
        except FetchError:
            if total is None:
                raise
            break
        batch = page.get("jobRequisitions") or []
        if total is None:
            total = int((page.get("meta") or {}).get("totalNumber") or 0)
        if not batch:
            break
        items.extend(batch)
    rows = [row for row in (_adp_row(item, board) for item in items) if near(row["location"])]
    return len(items), rows


# --- Paylocity ---------------------------------------------------------------

_PAYLOCITY_BOARD = "https://recruiting.paylocity.com/recruiting/jobs/All/{guid}"
_PAYLOCITY_JOB = "https://recruiting.paylocity.com/Recruiting/Jobs/Details/{job}"
_PAGE_DATA_RE = re.compile(r"window\.pageData\s*=\s*(?=\{)")


def paylocity_jobs(html: str) -> list[dict]:
    """Bluestone Lane, Oct 8 2026: the board page assigns its whole job list
    to window.pageData.Jobs; no pay or job type until the detail page."""
    match = _PAGE_DATA_RE.search(html or "")
    if not match:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(html, match.end())
    except ValueError:
        return []
    jobs = data.get("Jobs") if isinstance(data, dict) else None
    return [j for j in jobs or [] if isinstance(j, dict) and not j.get("IsInternal")]


def read_paylocity(board: dict, near: Near, fetch: Callable = fetch_html) -> tuple[int, list[dict]]:
    jobs = paylocity_jobs(fetch(_PAYLOCITY_BOARD.format(guid=board["guid"])))
    rows: list[dict] = []
    for job in jobs:
        where = job.get("JobLocation") or {}
        place = ", ".join(
            p for p in (str(where.get("City") or "").strip(), str(where.get("State") or "").strip())
            if p
        ) or str(job.get("LocationName") or "")
        if not job.get("JobId") or not near(place):
            continue
        url = _PAYLOCITY_JOB.format(job=job["JobId"])
        row = _row(job.get("JobTitle"), place, url, is_remote=bool(job.get("IsRemote")))
        posted = str(job.get("PublishedDate") or "")[:10]
        if posted:
            row["date_posted"] = posted
        if len(rows) < DETAIL_CAP:
            try:
                detail = pages.jobposting_rows(fetch(url), url)
            except FetchError as exc:
                logger.info("paylocity detail %s: %s", url, exc)
                detail = []
            if detail:
                for key in ("description", "salary_min", "salary_max", "salary_period",
                            "salary_currency", "employment"):
                    if detail[0].get(key) not in (None, ""):
                        row[key] = detail[0][key]
        rows.append(row)
    return len(jobs), rows


def read_board(
    board: Board,
    near: Near,
    *,
    fetch_json: Callable = fetch_json,
    fetch_html: Callable = fetch_html,
) -> tuple[int, list[dict]]:
    """(openings the board lists, rows near the saved place). Raises FetchError."""
    if board.kind == "rippling":
        return read_rippling(board.ref["slug"], near, fetch_json)
    if board.kind == "workday":
        return read_workday(board.ref, near, fetch_json)
    if board.kind == "adp":
        return read_adp(board.ref, near, fetch_json)
    if board.kind == "paylocity":
        return read_paylocity(board.ref, near, fetch_html)
    raise ValueError(f"unknown board {board.kind}")
