"""Project Casting, casting calls via the WordPress RSS feed plus SSR job pages.

The feed at ``https://www.projectcasting.com/feed`` is a standard WordPress
RSS 2.0 feed mixing casting-call articles with entertainment news; the
``Casting Calls`` category separates the two. Each casting article's
``content:encoded`` body links one or more real casting listings at
``projectcasting.com/job/<slug>`` (robots.txt allows ``/job/*``; the wp-json
API is 401-locked, so we never touch it). Those SSR job pages embed a JSON-LD
``JobPosting`` block with the actual casting company, structured location,
posting date, apply-by deadline, and structured pay, so each job link becomes
one enriched row. Articles without a job deep link fall back to a single row
pointing at the article itself.

Pay is emitted only when the JSON-LD ``baseSalary`` states a nonzero amount.
Prose pay lines in article bodies are never mined, by design for quest rows.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _clean_company_name,
    _parse_posted_date,
    _strip_html,
)

logger = logging.getLogger(__name__)

# Canonical host: the www form 301s here and the extra hop pushed slow
# responses past the timeout during live probing.
_FEED_URL = "https://projectcasting.com/feed"
_SOURCE = "projectcasting"
_PLATFORM = "Project Casting"

_CONTENT_TAG = "{http://purl.org/rss/1.0/modules/content/}encoded"
_CASTING_CATEGORY = "casting calls"

_JOB_LINK_RE = re.compile(
    r"https?://(?:www\.)?projectcasting\.com/job/([a-z0-9-]+)", re.IGNORECASE,
)
_LDJSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# Tight per-page timeout: a run can enrich a dozen-plus job pages and one
# slow page must not stall the sweep.
_ENRICH_TIMEOUT = 8

# The shared _HEADERS advertise Accept: application/json; this source serves
# RSS and HTML, so advertise what we actually want.
_FEED_HEADERS = {**_HEADERS, "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"}
_PAGE_HEADERS = {**_HEADERS, "Accept": "text/html, application/xhtml+xml;q=0.9, */*;q=0.8"}

# Section labels the feed attaches to every post; everything else is a
# topical tag (network, city, person) worth surfacing as quest extras.
_STRUCTURAL_CATEGORIES = frozenset({
    "casting calls", "casting call", "acting auditions",
    "free auditions", "free casting calls", "entertainment news", "news",
})

# City/region tags the site itself applies to casting posts. Used only as a
# location fallback when a row has no JSON-LD address.
_LOCATION_TAGS = frozenset({
    "new york", "new york city", "los angeles", "atlanta", "georgia",
    "chicago", "toronto", "vancouver", "canada", "new orleans", "louisiana",
    "miami", "texas", "boston", "philadelphia", "san francisco",
    "new jersey", "london", "united kingdom",
})

# Genuinely beginner-open markers, checked only against the enriched
# JobPosting title/description (background and extras work is open by nature).
_BEGINNER_OPEN_RE = re.compile(
    r"\bbackground\b|\bextras\b|no experience|open casting call|open call",
    re.IGNORECASE,
)


def _fetch_feed() -> str | None:
    """GET the RSS feed text; None on any failure.

    The WordPress origin is intermittently slow on a cold cache (observed
    live: 2s one minute, a 15s timeout the next), and every row depends on
    this one fetch, so a single retry is worth it.
    """
    for attempt in (1, 2):
        try:
            resp = requests.get(_FEED_URL, headers=_FEED_HEADERS, timeout=_TIMEOUT)
            if resp.status_code != 200:
                logger.warning("Project Casting feed returned %s", resp.status_code)
                return None
            return resp.text
        except requests.RequestException as exc:
            log_fn = logger.debug if attempt == 1 else logger.warning
            log_fn("Project Casting feed fetch failed (attempt %d): %s", attempt, exc)
    return None


def _fetch_job_page(url: str) -> str | None:
    """GET one SSR /job/ page; None on any failure."""
    try:
        resp = requests.get(url, headers=_PAGE_HEADERS, timeout=_ENRICH_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("Project Casting job page %s returned %s", url, resp.status_code)
            return None
        return resp.text
    except requests.RequestException as exc:
        logger.debug("Project Casting job page fetch failed (%s): %s", url, exc)
        return None


def _parse_feed(xml_text: str) -> list[dict]:
    """Parse RSS items into raw dicts; [] when the XML doesn't parse."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Project Casting feed XML unparseable: %s", exc)
        return []
    items: list[dict] = []
    for node in root.iter("item"):
        items.append({
            "title": (node.findtext("title") or "").strip(),
            "link": (node.findtext("link") or "").strip(),
            "pub_date": (node.findtext("pubDate") or "").strip(),
            "categories": [
                (c.text or "").strip() for c in node.findall("category") if c.text
            ],
            "content": node.findtext(_CONTENT_TAG) or "",
            "excerpt": node.findtext("description") or "",
        })
    return items


def _iso_date(rfc822: str) -> str:
    """RSS pubDate to ISO8601, or '' when unparseable."""
    if not rfc822:
        return ""
    try:
        return parsedate_to_datetime(rfc822).isoformat()
    except (TypeError, ValueError):
        return ""


def _location_from_tags(categories: list[str]) -> str:
    """Fallback location: the most specific location tag the post carries."""
    matches = [c for c in categories if c.lower() in _LOCATION_TAGS]
    return max(matches, key=len) if matches else ""


def _topical_tags(categories: list[str]) -> list[str]:
    return [c for c in categories if c.lower() not in _STRUCTURAL_CATEGORIES]


def _article_description(item: dict) -> str:
    """Plain-text description from the article body, boilerplate cut."""
    text = _strip_html(item["content"] or item["excerpt"])
    # WordPress appends a "The post ... appeared first on ..." footer.
    cut = text.find("The post ")
    return text[:cut].strip() if cut > 0 else text


def _find_job_posting(html: str) -> dict | None:
    """The JSON-LD JobPosting node from a /job/ page, or None."""
    for raw in _LDJSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for candidate in node.get("@graph", [node]):
                if not isinstance(candidate, dict):
                    continue
                node_type = candidate.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if "JobPosting" in types:
                    return candidate
    return None


def _ld_location(posting: dict) -> str:
    """'Locality, Region, Country' from JSON-LD jobLocation, deduped."""
    place = posting.get("jobLocation")
    if isinstance(place, list):
        place = place[0] if place else None
    address = place.get("address") if isinstance(place, dict) else None
    if not isinstance(address, dict):
        return ""
    parts: list[str] = []
    for key in ("addressLocality", "addressRegion", "addressCountry"):
        value = str(address.get(key) or "").strip()
        if value and value.upper() != "N/A" and value not in parts:
            parts.append(value)
    return ", ".join(parts)


_SALARY_PERIODS = {"HOUR": "hourly", "DAY": "daily", "WEEK": "weekly", "MONTH": "monthly", "YEAR": "yearly"}


def _ld_salary(posting: dict) -> tuple[float | None, float | None, str | None]:
    """(min, max, period) from JSON-LD baseSalary; Nones unless truly stated.

    Project Casting emits ``baseSalary`` with value 0 when the poster left
    structured pay blank, so zero means "not stated" and is dropped.
    """
    base = posting.get("baseSalary")
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return None, None, None

    def _num(raw: object) -> float | None:
        try:
            num = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return num if num > 0 else None

    lo = _num(value.get("minValue")) or _num(value.get("value"))
    hi = _num(value.get("maxValue")) or _num(value.get("value"))
    if lo is None and hi is None:
        return None, None, None
    period = _SALARY_PERIODS.get(str(value.get("unitText") or "").upper())
    return lo, hi, period


def _utcnow() -> datetime:
    """Wrapped so tests can freeze the clock."""
    return datetime.now(timezone.utc)


def _is_expired(row: dict) -> bool:
    """True when the listing's stated apply-by deadline has already passed.

    The feed republishes old calls inside roundup articles, so an enriched
    row can carry a validThrough that is weeks gone. Serving those as live
    quests would be dishonest; rows without a stated deadline are kept.
    """
    deadline = _parse_posted_date((row.get("quest") or {}).get("apply_by"))
    return deadline is not None and deadline < _utcnow()


def _enrich_row(row: dict) -> None:
    """Overlay JSON-LD JobPosting facts from the row's /job/ page, in place.

    Any failure (fetch, parse, missing block) leaves the RSS-derived row
    untouched, so enrichment is strictly additive.
    """
    html = _fetch_job_page(row["url"])
    if not html:
        return
    posting = _find_job_posting(html)
    if not posting:
        return

    title = str(posting.get("title") or "").strip()
    if title:
        row["title"] = title
    org = posting.get("hiringOrganization")
    company = str(org.get("name") or "").strip() if isinstance(org, dict) else ""
    if company:
        row["company"] = company
    location = _ld_location(posting)
    if location:
        row["location"] = location
    description = _strip_html(str(posting.get("description") or ""))
    if description:
        row["description"] = description
    date_posted = str(posting.get("datePosted") or "").strip()
    if date_posted:
        row["date_posted"] = date_posted

    lo, hi, period = _ld_salary(posting)
    if lo is not None or hi is not None:
        row["salary_min"] = lo
        row["salary_max"] = hi
        if period:
            row["salary_period"] = period
        row["salary_source"] = "reported"

    valid_through = str(posting.get("validThrough") or "").strip()
    if valid_through:
        row.setdefault("quest", {})["apply_by"] = valid_through

    if _BEGINNER_OPEN_RE.search(f"{row['title']} {row['description']}"):
        row["first_quest_ok"] = True


def _rows_from_item(item: dict) -> list[dict]:
    """Base row(s) for one casting-call feed item.

    One row per distinct /job/ deep link in the article body. An article
    with no deep link is journalism, not a posting, and produces no row:
    the old fallback published a scam-alert blog post as a casting call.
    """
    tags = _topical_tags(item["categories"])
    base = {
        "company": _PLATFORM,
        "location": _location_from_tags(item["categories"]),
        "source": _SOURCE,
        "vertical": "camera",
        "description": _article_description(item),
    }
    date_posted = _iso_date(item["pub_date"])
    if date_posted:
        base["date_posted"] = date_posted
    if tags:
        base["quest"] = {"tags": tags}

    def _clone() -> dict:
        row = dict(base)
        if "quest" in row:
            row["quest"] = dict(row["quest"])
        return row

    slugs: list[str] = []
    for slug in _JOB_LINK_RE.findall(item["content"]):
        if slug.lower() not in slugs:
            slugs.append(slug.lower())
    if not slugs:
        return []
    rows: list[dict] = []
    for slug in slugs:
        row = _clone()
        # Slug-derived placeholder; JSON-LD enrichment replaces it with the
        # listing's real title.
        row["title"] = _clean_company_name(slug)
        row["url"] = f"https://projectcasting.com/job/{slug}"
        rows.append(row)
    return rows


@register_scraper(
    name="projectcasting",
    display_name="Project Casting",
    url="https://www.projectcasting.com",
    description="Casting calls and auditions from Project Casting",
    category="quest",
    # calls post daily; deadlines run in days
    refresh_hours=24,
    enabled_by_default=False,
    vertical="camera",
)
def search_projectcasting(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch casting calls from the Project Casting RSS feed.

    ``roles`` is accepted for registry-signature parity but ignored: casting
    titles never word-match career roles, and this quest source only runs
    when explicitly invoked for the camera vertical.
    """
    logger.info("Fetching casting calls from Project Casting...")
    xml_text = _fetch_feed()
    if not xml_text:
        return []

    rows: list[dict] = []
    seen_urls: set[str] = set()
    for item in _parse_feed(xml_text):
        if _CASTING_CATEGORY not in {c.lower() for c in item["categories"]}:
            continue
        if not item["title"] or not item["link"]:
            continue
        for row in _rows_from_item(item):
            if row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            rows.append(row)

    results: list[dict] = []
    for row in rows:
        if len(results) >= max_results:
            break
        if "/job/" in row["url"]:
            _enrich_row(row)
            if _is_expired(row):
                continue
        results.append(row)

    logger.info("Project Casting: found %d casting calls", len(results))
    return results
