"""Currently actionable scholarships from Scholarship America.

Scholarship America exposes its public scholarship catalog through the site's
WordPress REST API.  The catalog's own ``Open`` taxonomy is not a sufficient
freshness signal: live verification on 2026-08-05 found many records still
tagged open after their stated close date.  This scraper therefore requires
the program-level application flag *and* independently parses the open and
close timestamps before publishing a row.

One catalog record uses a multi-year umbrella close date while its eligibility
copy lists shorter recurring application windows.  A window longer than 400
days is not actionable enough to represent as continuously open, so it drops
instead of guessing which sub-window applies.  The sponsor page remains the
canonical URL; it contains the full eligibility rules and links onward to the
application portal.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://scholarshipamerica.org/wp-json/wp/v2/scholarship"
_STATE_API_URL = "https://scholarshipamerica.org/wp-json/wp/v2/state"
_OPEN_STATUS_ID = 250
_VISIBLE_LISTING_ID = 246
_MAX_APPLICATION_WINDOW = timedelta(days=400)

_EXACT_RE = re.compile(r"^\$([\d,]+(?:\.\d{1,2})?)$")
_RANGE_RE = re.compile(
    r"^\$([\d,]+(?:\.\d{1,2})?)\s*(?:-|–|—|to)\s*\$?([\d,]+(?:\.\d{1,2})?)$",
    re.IGNORECASE,
)
_UP_TO_RE = re.compile(r"^up\s+to\s+\$([\d,]+(?:\.\d{1,2})?)$", re.IGNORECASE)
_AT_LEAST_RE = re.compile(
    r"^at\s+least\s+\$([\d,]+(?:\.\d{1,2})?)$", re.IGNORECASE
)


def _utcnow() -> datetime:
    """Wrapped so tests can freeze the clock."""
    return datetime.now(timezone.utc)


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def _award_fields(value: object) -> tuple[dict, str | None]:
    """Map only exact source-stated award shapes to numeric reward fields."""
    text = re.sub(r"\s+", " ", _strip_html(str(value or ""))).strip()
    if not text:
        return {}, None
    match = _RANGE_RE.fullmatch(text)
    if match:
        return {
            "salary_min": _number(match.group(1)),
            "salary_max": _number(match.group(2)),
            "salary_source": "reported",
        }, None
    match = _UP_TO_RE.fullmatch(text)
    if match:
        return {
            "salary_max": _number(match.group(1)),
            "salary_source": "reported",
        }, None
    match = _AT_LEAST_RE.fullmatch(text)
    if match:
        return {
            "salary_min": _number(match.group(1)),
            "salary_source": "reported",
        }, None
    match = _EXACT_RE.fullmatch(text)
    if match:
        amount = _number(match.group(1))
        return {
            "salary_min": amount,
            "salary_max": amount,
            "salary_source": "reported",
        }, None
    # Prose such as "multiple awards" stays verbatim; it never becomes a
    # number merely because it contains a dollar sign.
    return {}, text


def _parse_acf_datetime(value: object) -> datetime | None:
    if not isinstance(value, dict):
        return None
    raw = str(value.get("date_time") or "").strip()
    if not raw:
        return None
    try:
        local = datetime.strptime(raw, "%B %d, %Y %I:%M %p")
    except ValueError:
        return None
    zone_name = str(value.get("timezone_timezone_select_timezone") or "UTC")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    return local.replace(tzinfo=zone).astimezone(timezone.utc)


def _rich_text(value: object) -> str:
    """Flatten the ACF flexible-content shape without leaking layout labels."""
    if isinstance(value, str):
        return _strip_html(value)
    if isinstance(value, list):
        return " ".join(part for item in value if (part := _rich_text(item)))
    if isinstance(value, dict):
        ignored = {"acf_fc_layout", "section_heading_override"}
        return " ".join(
            part
            for key, item in value.items()
            if key not in ignored and (part := _rich_text(item))
        )
    return ""


def _excerpt(text: str, limit: int = 320) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > 80 else cut).rstrip(" ,;:")


def _fetch_records() -> list[dict]:
    payload = _get_json(
        _API_URL,
        params={
            "scholarship-status": _OPEN_STATUS_ID,
            "listing-status": _VISIBLE_LISTING_ID,
            "per_page": 100,
            "orderby": "modified",
            "order": "desc",
            "acf_format": "standard",
            "_fields": "id,link,title,state,acf",
        },
    )
    return payload if isinstance(payload, list) else []


def _fetch_state_names() -> dict[int, str]:
    payload = _get_json(
        _STATE_API_URL,
        params={"per_page": 100, "_fields": "id,name,slug"},
    )
    if not isinstance(payload, list):
        return {}
    names: dict[int, str] = {}
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        name = _strip_html(str(item.get("name") or ""))
        if name:
            names[item["id"]] = name
    return names


def _location(record: dict, state_names: dict[int, str]) -> str:
    ids = record.get("state")
    if not isinstance(ids, list):
        return ""
    names = [state_names[i] for i in ids if isinstance(i, int) and i in state_names]
    if any(name.lower() == "national" for name in names):
        return "United States"
    return "; ".join(dict.fromkeys(names))


def _normalize_record(
    record: dict,
    state_names: dict[int, str],
    *,
    now: datetime | None = None,
) -> dict | None:
    acf = record.get("acf")
    if not isinstance(acf, dict) or acf.get("scholarship_details_application_status") is not True:
        return None

    title_value = record.get("title")
    title = _strip_html(
        str(title_value.get("rendered") if isinstance(title_value, dict) else title_value or "")
    )
    url = str(record.get("link") or "").strip()
    if not title or not url.startswith("https://scholarshipamerica.org/scholarship/"):
        return None

    moment = now or _utcnow()
    opened = _parse_acf_datetime(acf.get("scholarship_details_open_date_time"))
    closes = _parse_acf_datetime(acf.get("scholarship_details_close_date_time"))
    # A parseable close is required because the site's Open taxonomy is known
    # to lag.  Future and past application windows are both non-actionable.
    if closes is None or closes < moment or (opened is not None and opened > moment):
        return None
    if opened is not None and closes - opened > _MAX_APPLICATION_WINDOW:
        logger.info("Skipping umbrella scholarship window for %s", title)
        return None

    hero = _rich_text(acf.get("scholarship_details_hero_description"))
    eligibility = _rich_text(acf.get("scholarship_content_eligibility"))
    requirements = _rich_text(acf.get("scholarship_content_requirements"))
    description = _excerpt(" ".join(part for part in (hero, eligibility, requirements) if part), 3000)
    if not description:
        return None

    salary_fields, pay_note = _award_fields(acf.get("scholarship_details_award_amount"))
    quest: dict[str, object] = {
        "bring": _excerpt(requirements, 320) or "the documents named in the application",
        "catch": (
            "eligibility is specific; verify every requirement and never pay to apply "
            "or send documents anywhere but the linked program"
        ),
        "apply_by": closes.date().isoformat(),
        "application_effort": "involved",
        "application_effort_note": (
            "Review the sponsor's eligibility rules and gather the listed supporting documents."
        ),
    }
    if eligibility:
        quest["criteria"] = [_excerpt(eligibility, 600)]
    if pay_note:
        quest["pay_note"] = pay_note

    row: dict = {
        "title": title,
        # Scholarship America administers these sponsor programs and hosts the
        # canonical eligibility page.  The sponsor itself remains in the title
        # and description when the source states it.
        "company": "Scholarship America",
        "location": _location(record, state_names),
        "url": url,
        "source": "scholarshipamerica",
        "vertical": "scholarship",
        "description": description,
        "event_end": closes.isoformat(),
        "is_rolling": False,
        "first_quest_ok": False,
        "quest": quest,
    }
    if opened is not None:
        row["date_posted"] = opened.date().isoformat()
        row["date_confidence"] = "exact"
    row.update(salary_fields)
    return row


@register_scraper(
    name="scholarshipamerica",
    display_name="Scholarship America",
    url="https://scholarshipamerica.org/students/browse-scholarships/",
    description="Open sponsor scholarships administered by Scholarship America, independently deadline-checked",
    category="scholarship",
    kind="scholarship",
    full_snapshot=True,
    refresh_hours=24,
    enabled_by_default=False,
    allowed_url_hosts=("scholarshipamerica.org",),
    allowed_url_paths=("/scholarship/",),
)
def search_scholarshipamerica(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch the currently actionable Scholarship America catalog rows."""
    records = _fetch_records()
    state_names = _fetch_state_names()
    moment = _utcnow()
    results: list[dict] = []
    seen: set[str] = set()
    for record in records:
        if len(results) >= max(0, max_results):
            break
        if not isinstance(record, dict):
            continue
        row = _normalize_record(record, state_names, now=moment)
        if row is None or row["url"] in seen:
            continue
        seen.add(row["url"])
        results.append(row)
    logger.info(
        "scholarshipamerica: %d actionable of %d catalog records",
        len(results),
        len(records),
    )
    return results
