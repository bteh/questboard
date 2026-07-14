"""Study Scavenger (body kind): paid clinical research listings via WP REST.

The listing arm of the long-running phase-1 community site JALR ("Just
Another Lab Rat"); recruiter-posted studies at real research units (ICON,
Pharmaron, CIS). Open WordPress REST API::

    GET https://studyscavenger.com/wp-json/wp/v2/posts?after=<iso>...

Compensation lives in the post body as the recruiter wrote it
("compensation up to $7,750 for time and travel"). Extraction is scoped
to sentences that actually say compensation/compensated, "up to $X" maps
to a maximum only, and posts with no stated figure carry no pay at all.
A 60-day window keeps closed studies off the board; per-visit stipends
inside long bodies are ignored on purpose.

Titles carry the site and city ("ICON (Lenexa, KS) Clinical Trial ...");
the parenthesized City, ST becomes the row's location.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json

logger = logging.getLogger(__name__)

_API_URL = "https://studyscavenger.com/wp-json/wp/v2/posts"
_FIELDS = "id,date,title,link,content"
_WINDOW_DAYS = 60

_TAG_RE = re.compile(r"<[^>]+>")
# Divi / WordPress page-builder shortcodes ([et_pb_section ...], [/et_pb_text],
# [vc_row], ...). They aren't HTML tags, so tag-stripping leaves them behind as
# "[et_pb_section fb_built=..." soup. Lowercase shortcode name only, so real
# bracketed text like "[Phase 2]" survives.
_SHORTCODE_RE = re.compile(r"\[/?[a-z][a-z0-9_]*(?:\s[^\]]*)?\]")
_CITY_RE = re.compile(r"\(([^()]{2,40},\s*[A-Z]{2})\)")
_COMP_RE = re.compile(
    r"compensat\w*[^.$]{0,80}?(up\s+to\s+)?\$\s*(\d[\d,]*(?:\.\d+)?)",
    re.IGNORECASE,
)


def _stated_comp(text: str) -> dict:
    """Salary fields from an explicit compensation sentence; {} when none."""
    m = _COMP_RE.search(text)
    if not m:
        return {}
    amount = float(m.group(2).replace(",", ""))
    if m.group(1):  # "up to $X" promises a ceiling, never a floor
        return {"salary_max": amount, "salary_source": "reported"}
    return {"salary_min": amount, "salary_max": amount, "salary_source": "reported"}


def _normalize_post(post: dict) -> dict | None:
    """One WP post to a body-kind quest row, or None to skip."""
    raw_title = (post.get("title") or {}).get("rendered") or ""
    title = re.sub(r"[​‌﻿]", "", html.unescape(raw_title))
    title = re.sub(r"\s+", " ", title).strip()
    link = post.get("link") or ""
    if not title or not link:
        return None

    # unescape first (so any encoded brackets become literal), then drop
    # page-builder shortcodes, then HTML tags, then collapse whitespace.
    raw = html.unescape((post.get("content") or {}).get("rendered") or "")
    raw = _SHORTCODE_RE.sub(" ", raw)
    text = _TAG_RE.sub(" ", raw)
    text = re.sub(r"\s+", " ", text).strip()

    city = _CITY_RE.search(title)
    row: dict = {
        "title": title,
        "company": "Study Scavenger",
        "location": city.group(1) if city else "",
        "url": link,
        "source": "studyscavenger",
        "vertical": "body",
        "description": text[:400],
        **_stated_comp(text),
    }
    if post.get("date"):
        row["date_posted"] = str(post["date"])
    return row


@register_scraper(
    name="studyscavenger",
    display_name="Study Scavenger",
    url="https://studyscavenger.com",
    description="Recruiter-posted paid clinical research studies from the JALR community's listing site",
    category="body",
    kind="body",
    # matches the 60-day fetch window: older posts fall out of the fetch
    stale_after_days=60,
    # listings arrive a few per week
    refresh_hours=24,
    allowed_url_hosts=("studyscavenger.com",),
    enabled_by_default=False,
)
def search_studyscavenger(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch recent paid research studies from Study Scavenger.

    ``roles`` is ignored on purpose: studies are not career titles.
    """
    logger.info("Fetching paid research studies from Study Scavenger...")
    after = (datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    data = _get_json(
        _API_URL,
        params={
            "per_page": str(min(max(max_results, 1), 100)),
            "after": after,
            "orderby": "date",
            "order": "desc",
            "_fields": _FIELDS,
        },
    )
    if not isinstance(data, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for post in data:
        if len(results) >= max_results:
            break
        if not isinstance(post, dict):
            continue
        row = _normalize_post(post)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("Study Scavenger: %d studies", len(results))
    return results
