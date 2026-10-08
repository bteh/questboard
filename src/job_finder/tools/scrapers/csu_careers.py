"""CSU Careers: every open job at the 23 California State University campuses.

CSU runs its system-wide job board on PageUp, which publishes the whole
current set as one RSS feed with full posting text
(careers.pageuppeople.com/873/cw/en-us/rss, linked from the feed's own
self link as latest_jobs.rss). robots.txt allows it and the board states no
automation ban. One GET per run is the polite path: the feed is the entire
board (~2,500 postings, ~38MB), and the alternative is one detail page per
posting to read pay.

Pay is stated in each posting's prose; see _public_sector.stated_pay_range.
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from job_finder.tools.scrapers._public_sector import (
    is_student_only,
    job_type_from,
    stated_pay_range,
    wants_california,
)
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _match_roles,
    _session,
    _strip_html,
    date_confidence_for,
    normalize_posted_date,
    rank_by_relevance,
)

logger = logging.getLogger(__name__)

FEED_URL = "https://careers.pageuppeople.com/873/cw/en-us/rss"
_JOB_NS = "{http://pageuppeople.com/}"
_FEED_TIMEOUT = 60
_CAMPUS_FILE = Path(__file__).parent / "data" / "csu_campuses.json"
_FALLBACK_EMPLOYER = "California State University"

_CAMPUSES: dict[str, dict[str, str]] | None = None


def _campuses() -> dict[str, dict[str, str]]:
    global _CAMPUSES
    if _CAMPUSES is None:
        try:
            data = json.loads(_CAMPUS_FILE.read_text(encoding="utf-8"))
            _CAMPUSES = dict(data.get("campuses") or {})
        except (OSError, ValueError) as exc:
            logger.warning("CSU campus map unreadable (%s); using system name", exc)
            _CAMPUSES = {}
    return _CAMPUSES


def campus_for(raw_location: str | None) -> tuple[str, str]:
    """(employer, location) for a feed location like 'Southern California|Pomona'.

    Multi-campus postings list several labels; the first names the employer.
    """
    first = (raw_location or "").split(",")[0]
    label = first.split("|", 1)[-1].strip()
    entry = _campuses().get(label)
    if entry:
        return entry["employer"], entry["city"]
    if label:
        logger.info("CSU Careers: unmapped campus label %r", label)
    return _FALLBACK_EMPLOYER, "California"


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None and node.text else ""


def _time_basis(item: ET.Element) -> str:
    for node in item.findall(f"{_JOB_NS}category"):
        for part in (node.text or "").split(","):
            key, _, value = part.partition("|")
            if key.strip() == "Time Basis":
                return job_type_from(value)
    return ""


def parse_feed(
    xml_bytes: bytes,
    roles: list[str] | None,
    *,
    match_mode: str = "all_significant",
    include_founding: bool = True,
) -> list[dict]:
    """Role-matched, open-to-the-public rows from one CSU Careers RSS payload."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning("CSU Careers: feed is not valid XML: %s", exc)
        return []

    rows: list[dict] = []
    for item in root.iter("item"):
        title = _text(item, "title")
        if not title:
            continue
        if roles and not _match_roles(
            title, roles, match_mode=match_mode, include_founding=include_founding,
        ):
            continue
        work_type = _text(item, f"{_JOB_NS}workType")
        if is_student_only(work_type):
            continue

        employer, location = campus_for(_text(item, f"{_JOB_NS}location"))
        body_html = _text(item, f"{_JOB_NS}description") or _text(item, "description")
        description = _strip_html(body_html) if body_html else ""
        posted = _text(item, "pubDate")

        row: dict = {
            "title": title,
            "company": employer,
            "location": location,
            "url": _text(item, "link"),
            "source": "csu_careers",
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "date_posted": normalize_posted_date(posted),
            "date_confidence": date_confidence_for(posted),
            "is_remote": False,
            "company_size": "",
            "job_type": _time_basis(item),
        }
        pay = stated_pay_range(description)
        if pay:
            row["salary_min"], row["salary_max"], row["salary_period"] = pay
            row["salary_currency"] = "USD"
        rows.append(row)
    return rows


def _fetch_feed() -> bytes | None:
    try:
        resp = _session().get(
            FEED_URL,
            timeout=_FEED_TIMEOUT,
            headers={"Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.1"},
        )
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.warning("CSU Careers: feed fetch failed: %s", exc)
        return None


@register_scraper(
    name="csu_careers",
    display_name="CSU Careers",
    url="https://csucareers.calstate.edu",
    description="Staff and faculty jobs at all 23 Cal State campuses, with stated pay",
    category="public",
    kind="career",
    allowed_url_hosts=("pageuppeople.com", "calstate.edu"),
)
def search_csu_careers(
    roles: list[str] | None = None,
    max_results: int = 100,
    locations: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    if not wants_california(locations):
        logger.info("CSU Careers: no California place saved; skipping")
        return []
    payload = _fetch_feed()
    if not payload:
        return []
    rows = parse_feed(
        payload, roles, match_mode=match_mode, include_founding=include_founding,
    )
    logger.info("CSU Careers: %d role-matched postings", len(rows))
    return rank_by_relevance(rows, roles)[:max_results]
