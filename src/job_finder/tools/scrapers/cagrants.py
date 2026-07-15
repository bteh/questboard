"""California Grants Portal (pitch kind): state grants open to businesses.

The state's official grants dataset on data.ca.gov (CKAN datastore,
refreshed daily). One filtered query returns every active grant, so
this is a full snapshot: absence from a healthy run proves closure::

    GET https://data.ca.gov/api/3/action/datastore_search
        ?resource_id=111c8c88-21f6-453c-ae2c-b4785a0624f5
        &filters={"Status": "active"}

Live-verified quirks (2026-07-12, 174 active records; eligibility gate
re-verified live 2026-07-15, 177 active records):

- ``ApplicantType`` is a semicolon list drawn from six portal values:
  Business, Individual, Nonprofit, Public Agency, Tribal Government,
  Other Legal Entity. The board's seekers are individuals and small
  businesses (docs/icp.md), so only grants naming Business or
  Individual publish. Nonprofit-only grants stay out of scope for the
  pilot, and rows stating only government entities (Public Agency,
  Tribal Government, Other Legal Entity) drop.
- ``ApplicantType`` alone is too coarse: facility-compliance programs
  state Business even though only the owner or operator of a regulated
  facility can apply. The live example is the RUST underground storage
  tank family, whose own Purpose and ApplicantTypeNotes require a UST
  owner/operator bringing fuel tanks up to Health and Safety Code. The
  portal's ``Categories`` values are broad topics ("Environment &
  Water") with no applicant-fit value, so there is no clean stated
  category to exclude. In its place, a narrow stated-text exclusion
  drops rows whose own Title, Purpose, or ApplicantTypeNotes carry a
  facility-compliance marker (underground storage tanks, marina
  ownership, pollution control facilities). Live 2026-07-15 that drops
  exactly 7 rows, every one a facility-owner program: the RUST grant
  and loan, the UST Cleanup Fund, the Orphan Site Cleanup Fund, two
  marina pumpout grants, and CPCFA facility bonds.
- ``ApplicationDeadline`` is a datetime or the literal "Ongoing".
  Ongoing rows publish with no apply_by and say so in the description.
  A dated deadline already past drops the row (the dataset can lag).
- ``EstAmounts`` is prose. Only an exact stated range ("Between $X and
  $Y") maps to salary_min/max, and an exact "Up to $X" to a ceiling
  only. Every other phrasing rides verbatim in ``quest.pay_note`` with
  no salary keys. ``EstAvailFunds`` is the program's total pot, never a
  per-award figure, so it goes in the description.
- ``GrantURL`` is each agency's own apply page, spanning many *.ca.gov
  subdomains plus occasional vendor and CDN hosts, so there is no host
  gate (the bankrewards precedent: the source points outward by
  design). In its place every row must carry an https URL; the rare
  http:// rows drop.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json

logger = logging.getLogger(__name__)

_API_URL = "https://data.ca.gov/api/3/action/datastore_search"
_RESOURCE_ID = "111c8c88-21f6-453c-ae2c-b4785a0624f5"
_PAGE_LIMIT = 500
_MAX_PAGES = 10

_RANGE_RE = re.compile(r"^between\s+\$([\d,]+)\s+and\s+\$([\d,]+)$", re.IGNORECASE)
_UP_TO_RE = re.compile(r"^up\s+to\s+\$([\d,]+)$", re.IGNORECASE)
_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _utcnow() -> datetime:
    """Wrapped so tests can freeze the clock."""
    return datetime.now(timezone.utc)


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fetch_records() -> list[dict]:
    records: list[dict] = []
    for page in range(_MAX_PAGES):
        data = _get_json(
            _API_URL,
            params={
                "resource_id": _RESOURCE_ID,
                "filters": json.dumps({"Status": "active"}),
                "limit": _PAGE_LIMIT,
                "offset": page * _PAGE_LIMIT,
            },
        )
        if not isinstance(data, dict) or not data.get("success"):
            break
        result = data.get("result")
        page_records = result.get("records") if isinstance(result, dict) else None
        if not isinstance(page_records, list) or not page_records:
            break
        records.extend(page_records)
        if len(page_records) < _PAGE_LIMIT:
            break
    return records


_ELIGIBLE_APPLICANT_TYPES = {"business", "individual"}

# facility-owner compliance programs state these in their own Title,
# Purpose, or ApplicantTypeNotes; ApplicantType alone passes them
# (see the module docstring)
_FACILITY_MARKERS = (
    "underground storage tank",
    "marina owners",
    "pollution control",
)


def _applicant_type_fits(record: dict) -> bool:
    """The portal states an applicant type the board's seekers can be."""
    tokens = str(record.get("ApplicantType") or "").split(";")
    return any(t.strip().lower() in _ELIGIBLE_APPLICANT_TYPES for t in tokens)


def _facility_compliance(record: dict) -> bool:
    """The record's own stated text marks a facility-owner program."""
    stated = " ".join(
        str(record.get(key) or "")
        for key in ("Title", "Purpose", "ApplicantTypeNotes")
    ).lower()
    return any(marker in stated for marker in _FACILITY_MARKERS)


def _parse_est_amounts(text: str | None) -> tuple[dict, str | None]:
    """(salary fields, pay note) from the EstAmounts prose.

    Only an exact stated range or an exact "Up to $X" becomes numbers;
    a ceiling is never a floor, and any other phrasing is the source's
    own words, kept verbatim instead of a number we invented.
    """
    text = _clean(text)
    if not text:
        return {}, None
    m = _RANGE_RE.match(text)
    if m:
        return {
            "salary_min": float(m.group(1).replace(",", "")),
            "salary_max": float(m.group(2).replace(",", "")),
            "salary_source": "reported",
        }, None
    m = _UP_TO_RE.match(text)
    if m:
        return {
            "salary_max": float(m.group(1).replace(",", "")),
            "salary_source": "reported",
        }, None
    return {}, text


def _parse_date(value: object) -> date | None:
    m = _DATE_PREFIX_RE.match(str(value or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _normalize_record(record: dict) -> dict | None:
    """One dataset record to a pitch-kind quest row, or None to skip."""
    if not _applicant_type_fits(record) or _facility_compliance(record):
        return None
    title = _clean(record.get("Title"))
    agency = _clean(record.get("AgencyDept"))
    url = str(record.get("GrantURL") or "").strip()
    if not title or not agency or not url.startswith("https://"):
        return None

    deadline_raw = _clean(record.get("ApplicationDeadline"))
    ongoing = deadline_raw.lower() == "ongoing"
    apply_by: str | None = None
    if not ongoing:
        deadline = _parse_date(deadline_raw)
        if deadline is not None:
            if deadline < _utcnow().date():
                return None
            apply_by = deadline.isoformat()

    salary_fields, pay_note = _parse_est_amounts(record.get("EstAmounts"))

    parts = [_clean(record.get("Purpose")) or _clean(record.get("Description"))]
    funds = _clean(record.get("EstAvailFunds"))
    if funds:
        parts.append(f"Estimated available funds {funds}.")
    if ongoing:
        parts.append("Applications accepted on an ongoing basis.")

    row: dict = {
        "title": title,
        "company": agency,
        "location": "",
        "url": url,
        "source": "cagrants",
        "vertical": "pitch",
        "description": " ".join(p for p in parts if p),
    }
    row.update(salary_fields)
    quest: dict = {}
    if apply_by:
        quest["apply_by"] = apply_by
    if pay_note:
        quest["pay_note"] = pay_note
    if quest:
        row["quest"] = quest
    opened = _parse_date(record.get("OpenDate"))
    if opened is not None:
        row["date_posted"] = opened.isoformat()
    return row


@register_scraper(
    name="cagrants",
    display_name="California Grants Portal",
    url="https://www.grants.ca.gov",
    description="California state grants open to individuals and small businesses, from the official data.ca.gov dataset",
    category="pitch",
    kind="pitch",
    # one filtered query returns every active grant, so absence proves closure
    full_snapshot=True,
    # the dataset refreshes daily
    refresh_hours=24,
    # GrantURL points at each agency's own apply page across many *.ca.gov
    # subdomains and occasional vendor hosts, so no host gate (bankrewards
    # precedent); rows must be https instead
    allowed_url_hosts=None,
    enabled_by_default=False,
    # off-ICP for the builder-funding lane (state grants for CA businesses,
    # not funding for young founders/students); kept as code, off the board
    research_only=True,
)
def search_cagrants(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch active grants the board's seekers can apply for from the California Grants Portal.

    ``roles`` is ignored on purpose: grants are not career titles.
    """
    logger.info("Fetching active grants from the California Grants Portal...")
    records = _fetch_records()

    results: list[dict] = []
    seen: set[str] = set()
    for record in records:
        if len(results) >= max_results:
            break
        if not isinstance(record, dict):
            continue
        row = _normalize_record(record)
        if row is None:
            continue
        key = str(record.get("PortalID") or "") or row["url"]
        if key in seen:
            continue
        seen.add(key)
        results.append(row)

    logger.info("California Grants Portal: %d eligible grants", len(results))
    return results
