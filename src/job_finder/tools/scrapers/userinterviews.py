"""User Interviews (think kind): public paid-research listings API.

The best-liked paid-research platform on r/beermoney, and it serves its
public browse page from an open JSON:API endpoint::

    GET https://www.userinterviews.com/api/project_listings?page[size]=50

Live-verified (2026-07-09): no auth, no cookies, compensation stated on
every listing (participantCompensationAmount plus a human incentive
string like "$45.00 via choice of dozens of digital gift cards").

Gates: private listings and listings with no incentive are skipped (the
board carries quests that pay). Compensation type is often gift cards,
not cash; the incentive string goes in the description verbatim so
nobody discovers that after applying. Study run windows map to
event_end (never event_start: a study mid-window is still joinable, and
an event_start in the past would wrongly hide it).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json

logger = logging.getLogger(__name__)

_API_URL = "https://www.userinterviews.com/api/project_listings"
_SITE = "https://www.userinterviews.com"

_RANGE_END_RE = re.compile(r"-\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s*$")


def _range_end(run_range: str | None) -> datetime | None:
    """The end date of "10 Jul 2026 - 29 Jul 2026", or None."""
    if not run_range:
        return None
    m = _RANGE_END_RE.search(run_range)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%d %b %Y")
    except ValueError:
        return None


def _normalize_listing(item: dict) -> dict | None:
    """One JSON:API projectListing to a think-kind quest row, or None."""
    attrs = item.get("attributes")
    if not isinstance(attrs, dict):
        return None
    if attrs.get("isPrivate") or attrs.get("noIncentive"):
        return None
    comp = attrs.get("participantCompensationAmount")
    if not isinstance(comp, (int, float)) or comp <= 0:
        return None
    title = (attrs.get("publicTitle") or "").strip()
    apply_path = (attrs.get("applyUrl") or "").strip()
    if not title or not apply_path:
        return None

    interview = (attrs.get("interviewTypeName") or "").strip()
    is_remote = interview.lower() == "online"
    location = (attrs.get("locationShortString") or "").strip()
    if not location and is_remote:
        location = "Remote"

    parts = []
    study_type = (attrs.get("studyTypeName") or "").strip()
    time_str = (attrs.get("estimatedTime") or "").strip()
    if study_type:
        parts.append(f"{study_type}.")
    if time_str:
        parts.append(f"Takes {time_str}.")
    incentive = (attrs.get("incentive") or "").strip()
    if incentive:
        parts.append(f"Pays {incentive}.")
    desc = (attrs.get("publicDescription") or "").strip()
    if desc:
        parts.append(desc)
    description = " ".join(parts)

    row: dict = {
        "title": title,
        "company": (attrs.get("teamName") or "User Interviews").strip(),
        "location": location,
        "is_remote": is_remote,
        "remote_flag_reported": True,
        "url": _SITE + apply_path if apply_path.startswith("/") else apply_path,
        "source": "userinterviews",
        "vertical": "think",
        "description": description,
        "salary_min": float(comp),
        "salary_max": float(comp),
        "salary_period": "session",
        "salary_source": "reported",
    }
    end = _range_end(attrs.get("runDateRangeString"))
    if end is not None:
        row["event_end"] = end
    if incentive:
        row["quest"] = {"pay_note": incentive}
    return row


@register_scraper(
    name="userinterviews",
    display_name="User Interviews",
    url="https://www.userinterviews.com/studies",
    description="Paid research studies with stated per-session compensation from the public listings API",
    category="think",
    kind="think",
    enabled_by_default=False,
)
def search_userinterviews(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch public paid-research listings from User Interviews.

    ``roles`` is ignored on purpose: studies are not career titles.
    """
    logger.info("Fetching paid studies from User Interviews...")
    data = _get_json(
        _API_URL,
        params={"page[size]": str(min(max(max_results, 1), 50))},
    )
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for item in items:
        if len(results) >= max_results:
            break
        if not isinstance(item, dict):
            continue
        row = _normalize_listing(item)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("User Interviews: %d paid studies", len(results))
    return results
