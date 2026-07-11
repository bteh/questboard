"""Trialmed (body kind): PPD's clinic-network volunteer studies via WP REST.

Trialmed is Thermo Fisher/PPD's participant-facing surface for its US
phase-1 clinics (ppd.com's participate link redirects here). Open
WordPress REST API, live-probed 2026-07-10::

    GET https://trialmed.com/wp-json/wp/v2/studies?per_page=100

60 studies total on probe day (single page; ``?page=N`` handles growth).
Each study's ``content.rendered`` carries a stable summary ``<dl>`` with
Check-in/Start date, Therapy area(s), Location (clinic city), Compensation,
and Status. The study ``link`` is the detail page and the apply surface.

Gates that keep the board honest:

- Status must be "Enrolling now". "Coming soon" and "Register interest
  now" studies have nothing to act on yet.
- The clinic must be US. The network spans the US, UK (Manchester,
  Glasgow, Midlands, Merseyside, Cardiff), Poland, and Czechia; one fetch
  of ``/wp-json/wp/v2/clinics`` maps clinic names to their country, and
  only studies at a US clinic city pass. Multi-clinic studies list "N
  clinics" instead of a city, so their country can't be verified and
  they're skipped too. Note the trap: the clinic NAMED "Birmingham" is
  Birmingham, AL (US); the UK Birmingham site is named "Midlands".

Pay honesty: "Up to $X" maps to salary_max ONLY (a ceiling is never a
floor). "Compensation varies by study" and every other non-"Up to" line
emit no salary keys at all. The verbatim compensation line always rides
in quest.pay_note and the description. A parseable check-in date becomes
event_start; "Flexible start date" / "Multiple start dates" do not.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _parse_posted_date

logger = logging.getLogger(__name__)

_STUDIES_URL = "https://trialmed.com/wp-json/wp/v2/studies"
_CLINICS_URL = "https://trialmed.com/wp-json/wp/v2/clinics"
_FIELDS = "id,date,modified,slug,link,title,content"
_PER_PAGE = 100
_MAX_PAGES = 10

_TAG_RE = re.compile(r"<[^>]+>")
_DL_ITEM_RE = re.compile(
    r'study-summary-def-list-term">\s*(.*?)\s*</dt>.*?'
    r'study-summary-def-list-definition">\s*(.*?)\s*</dd>',
    re.DOTALL,
)
_UP_TO_RE = re.compile(r"^up\s+to\s+\$\s*(\d[\d,]*(?:\.\d+)?)\s*\.?$", re.IGNORECASE)
_START_DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?",
    re.IGNORECASE,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"))}


def _clean(text: str) -> str:
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = re.sub(r"[​‌﻿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _summary_fields(rendered: str) -> dict[str, str]:
    """The study summary <dl> as {term: definition}, tags stripped."""
    return {_clean(k): _clean(v) for k, v in _DL_ITEM_RE.findall(rendered)}


def _fetch_us_cities() -> dict[str, str]:
    """Clinic name (casefolded) -> "City, ST" for US clinics only."""
    data = _get_json(_CLINICS_URL, params={"per_page": "50"})
    if not isinstance(data, list):
        return {}
    cities: dict[str, str] = {}
    for clinic in data:
        if not isinstance(clinic, dict):
            continue
        meta = clinic.get("meta") or {}
        country = str(meta.get("trialmed_business_address_country") or "").strip()
        if country.upper() != "US":
            continue
        name = _clean((clinic.get("title") or {}).get("rendered") or "")
        if not name:
            continue
        city = str(meta.get("trialmed_business_address_city") or "").strip() or name
        state = str(meta.get("trialmed_business_address_state") or "").strip()
        cities[name.casefold()] = f"{city}, {state}" if state else city
    return cities


def _stated_comp(line: str) -> dict:
    """Salary fields from the compensation line; "Up to $X" is a ceiling only."""
    m = _UP_TO_RE.match(line)
    if not m:
        return {}
    return {
        "salary_max": float(m.group(1).replace(",", "")),
        "salary_source": "reported",
    }


def _parse_start(value: str, anchor: datetime | None) -> str | None:
    """ISO date from a check-in line like "Starts Oct 28th", or None.

    A yearless date takes the anchor's (post date's) year, rolling forward
    a year when that would put the start before the post.
    """
    m = _START_DATE_RE.search(value)
    if not m:
        return None
    month = _MONTHS[m.group(1)[:3].lower()]
    day = int(m.group(2))
    anchor = anchor or datetime.now(timezone.utc)
    year = int(m.group(3)) if m.group(3) else anchor.year
    try:
        start = datetime(year, month, day)
    except ValueError:
        return None
    if not m.group(3) and start.date() < anchor.date():
        start = start.replace(year=year + 1)
    return start.strftime("%Y-%m-%d")


def _normalize_study(study: dict, us_cities: dict[str, str]) -> dict | None:
    """One WP study to a body-kind quest row, or None to skip."""
    title = _clean((study.get("title") or {}).get("rendered") or "")
    link = study.get("link") or ""
    if not title or not link:
        return None

    fields = _summary_fields((study.get("content") or {}).get("rendered") or "")
    if fields.get("Status", "").casefold() != "enrolling now":
        return None
    location = us_cities.get(fields.get("Location", "").casefold())
    if not location:
        return None

    checkin = fields.get("Check-in date") or fields.get("Start date") or ""
    comp = fields.get("Compensation", "")

    parts = []
    therapy = fields.get("Therapy area(s)", "")
    if therapy:
        parts.append(f"{therapy} study.")
    if checkin:
        parts.append(f"Check-in: {checkin}.")
    if comp:
        parts.append(comp if comp.endswith(".") else f"{comp}.")

    row: dict = {
        "title": title,
        "company": "Trialmed (PPD)",
        "location": location,
        "url": link,
        "source": "trialmed",
        "vertical": "body",
        "description": " ".join(parts),
        **_stated_comp(comp),
    }
    if study.get("date"):
        row["date_posted"] = str(study["date"])
    start = _parse_start(checkin, _parse_posted_date(study.get("date")))
    if start:
        row["event_start"] = start
    if comp:
        row["quest"] = {"pay_note": comp}
    return row


@register_scraper(
    name="trialmed",
    display_name="Trialmed (PPD clinics)",
    url="https://trialmed.com",
    description="Paid clinical studies at PPD's US phase-1 clinics, with stated compensation ceilings",
    category="body",
    kind="body",
    # one paginated fetch is the source's whole set: closed studies leave the table
    full_snapshot=True,
    # phase-1 slots fill fast; twice a day keeps the enrolling set real
    refresh_hours=12,
    allowed_url_hosts=("trialmed.com",),
    enabled_by_default=False,
)
def search_trialmed(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch enrolling US studies from Trialmed.

    ``roles`` is ignored on purpose: studies are not career titles.
    """
    logger.info("Fetching PPD clinic studies from Trialmed...")
    us_cities = _fetch_us_cities()
    if not us_cities:
        # without clinic countries no study can be verified as US
        logger.warning("Trialmed: clinic list unavailable, emitting nothing")
        return []

    studies: list[dict] = []
    page = 1
    while page <= _MAX_PAGES:
        batch = _get_json(
            _STUDIES_URL,
            params={
                "per_page": str(_PER_PAGE),
                "page": str(page),
                "_fields": _FIELDS,
            },
        )
        if not isinstance(batch, list) or not batch:
            break
        studies.extend(s for s in batch if isinstance(s, dict))
        if len(batch) < _PER_PAGE:
            break
        page += 1

    results: list[dict] = []
    seen_urls: set[str] = set()
    for study in studies:
        if len(results) >= max_results:
            break
        row = _normalize_study(study, us_cities)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("Trialmed: %d enrolling US studies", len(results))
    return results
