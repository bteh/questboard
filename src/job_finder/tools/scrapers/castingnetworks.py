"""Casting Networks - public casting calls via JSON-LD JobPosting blocks.

The public listing at ``https://www.castingnetworks.com/casting-calls/``
embeds a schema.org ItemList of role deep links, and each role page embeds a
full JobPosting block (title, description, datePosted, validThrough,
hiringOrganization, jobLocation when stated, baseSalary when stated). Probed
live 2026-07-08: plain GETs return HTTP 200, no Cloudflare challenge; the
listing carried 8 open roles. ``hiringOrganization.name`` is the platform
itself ("Casting Networks") on every probed role, never the production
company, so ``company`` reads as the platform.

Quest vertical: "camera". Career role keywords do not map onto casting-call
titles, so ``roles`` is accepted for registry compatibility and ignored.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _strip_html

logger = logging.getLogger(__name__)

_LISTING_URL = "https://www.castingnetworks.com/casting-calls/"
_ROLE_PATH_MARKER = "/talent/project/"
_MAX_WORKERS = 6
_PAGE_TIMEOUT = 10

# The shared headers advertise JSON; these pages are HTML.
_HTML_HEADERS = {**_HEADERS, "Accept": "text/html,application/xhtml+xml"}

_LD_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)

# Dash class for stated age ranges: hyphen, en dash, em dash (unicode
# escapes so the literal characters never appear in this file).
_DASH = "[-\u2013\u2014]"
_AGE_RANGE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\bages?\s*:?\s*(\d{{1,2}})\s*(?:{_DASH}|to\s)\s*(\d{{1,2}})\b"),
    re.compile(rf"\b(\d{{1,2}})\s*(?:{_DASH}|to\s)\s*(\d{{1,2}})\s*(?:years?|yrs?)\s*(?:of\s+age|old)\b"),
)
_AGE_MIN_RE = re.compile(r"\bages?\s+(\d{1,2})\s*\+")

# Explicit beginner-open statements only; background/extras work is often
# beginner-open in practice, but we never claim it unless the call says so.
_FIRST_QUEST_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bno\s+(?:prior\s+|previous\s+|acting\s+|modeling\s+|professional\s+)?"
        r"experience\s+(?:is\s+)?(?:necessary|needed|required)\b"
    ),
    re.compile(r"\bexperience\s+(?:is\s+)?not\s+(?:necessary|needed|required)\b"),
)

_NON_UNION_RE = re.compile(r"\bnon[- ]?union\b")

# schema.org baseSalary unitText values -> our salary_period vocabulary.
_PERIOD_BY_UNIT = {
    "HOUR": "hourly", "DAY": "daily", "WEEK": "weekly", "MONTH": "monthly", "YEAR": "yearly",
}


def _get_html(url: str) -> str:
    """GET a page's HTML; '' on any failure so callers degrade gracefully."""
    try:
        resp = requests.get(url, headers=_HTML_HEADERS, timeout=_PAGE_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Casting Networks %s returned %s", url, resp.status_code)
            return ""
        return resp.text
    except requests.RequestException as exc:
        logger.warning("Casting Networks fetch failed (%s): %s", url, exc)
        return ""


def _ld_nodes(html: str) -> list[dict]:
    """All JSON-LD nodes on a page, with @graph containers flattened."""
    nodes: list[dict] = []
    for raw in _LD_JSON_RE.findall(html):
        try:
            block = json.loads(raw.strip())
        except ValueError:
            continue
        for entry in block if isinstance(block, list) else [block]:
            if not isinstance(entry, dict):
                continue
            nodes.append(entry)
            graph = entry.get("@graph")
            if isinstance(graph, list):
                nodes.extend(n for n in graph if isinstance(n, dict))
    return nodes


def _has_type(node: dict, type_name: str) -> bool:
    """True if a node's @type (string or list) includes ``type_name``."""
    node_type = node.get("@type")
    if isinstance(node_type, list):
        return type_name in node_type
    return node_type == type_name


def _listing_role_urls(html: str) -> list[str]:
    """Role deep links from the listing page's ItemList, listing order kept."""
    urls: list[str] = []
    seen: set[str] = set()
    for node in _ld_nodes(html):
        item_lists = [node] if _has_type(node, "ItemList") else []
        main = node.get("mainEntity")
        if isinstance(main, dict) and _has_type(main, "ItemList"):
            item_lists.append(main)
        for lst in item_lists:
            for el in lst.get("itemListElement") or []:
                if not isinstance(el, dict):
                    continue
                item = el.get("item")
                url = item.get("url") if isinstance(item, dict) else None
                if not isinstance(url, str) or _ROLE_PATH_MARKER not in url:
                    continue
                key = url.rstrip("/")
                if key not in seen:
                    seen.add(key)
                    urls.append(url)
    return urls


def _find_jobposting(html: str) -> dict | None:
    """The page's JobPosting node, or None when the page carries none."""
    for node in _ld_nodes(html):
        if _has_type(node, "JobPosting"):
            return node
    return None


def _format_location(job_location: object) -> str:
    """Human location from a schema.org jobLocation, '' when not stated."""
    place = job_location[0] if isinstance(job_location, list) and job_location else job_location
    if not isinstance(place, dict):
        return ""
    address = place.get("address")
    if not isinstance(address, dict):
        return ""
    parts = [
        str(p).strip()
        for p in (address.get("addressLocality"), address.get("addressRegion"))
        if p and str(p).strip()
    ]
    if parts:
        return ", ".join(parts)
    country = address.get("addressCountry")
    return str(country).strip() if country else ""


def _num(value: object) -> float | None:
    try:
        val = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def _extract_salary(base: object) -> tuple[float | None, float | None, str | None]:
    """(min, max, period) from a schema.org baseSalary, all-None when absent."""
    if not isinstance(base, dict):
        return None, None, None
    value = base.get("value")
    unit = None
    lo = hi = None
    if isinstance(value, dict):
        unit = value.get("unitText")
        lo = _num(value.get("minValue"))
        hi = _num(value.get("maxValue"))
        if lo is None and hi is None:
            lo = hi = _num(value.get("value"))
    else:
        lo = hi = _num(value)
    if lo is None and hi is None:
        return None, None, None
    return lo, hi, _PERIOD_BY_UNIT.get(str(unit or "").upper())


def _extract_ages(low: str) -> tuple[int | None, int | None]:
    """Stated age bounds ("Ages 18 to 30", "ages 25-55", "ages 18+")."""
    for rx in _AGE_RANGE_RES:
        m = rx.search(low)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b < 100:
                return a, b
    m = _AGE_MIN_RE.search(low)
    if m:
        a = int(m.group(1))
        if 0 < a < 100:
            return a, None
    return None, None


def _normalize_posting(posting: dict, page_url: str) -> dict | None:
    """Map one JobPosting node to a quest row, or None on a bad node."""
    title = str(posting.get("title") or "").strip()
    url = posting.get("url")
    if not isinstance(url, str) or not url.startswith("http"):
        url = page_url
    if not title or not url:
        return None

    org = posting.get("hiringOrganization")
    company = str(org.get("name") or "").strip() if isinstance(org, dict) else ""
    raw_description = str(posting.get("description") or "")
    low = f"{title}\n{raw_description}".lower()

    row: dict = {
        "title": title,
        "company": company,
        "location": _format_location(posting.get("jobLocation")),
        "url": url,
        "source": "castingnetworks",
        "vertical": "camera",
        "description": _strip_html(raw_description),
    }

    date_posted = posting.get("datePosted")
    if isinstance(date_posted, str) and date_posted:
        row["date_posted"] = date_posted

    lo, hi, period = _extract_salary(posting.get("baseSalary"))
    if lo is not None or hi is not None:
        row["salary_min"] = lo
        row["salary_max"] = hi
        if period:
            row["salary_period"] = period
        row["salary_source"] = "reported"

    if any(rx.search(low) for rx in _FIRST_QUEST_RES):
        row["first_quest_ok"] = True

    quest: dict = {}
    identifier = posting.get("identifier")
    if isinstance(identifier, dict) and identifier.get("value"):
        quest["role_id"] = str(identifier["value"])
    valid_through = posting.get("validThrough")
    if isinstance(valid_through, str) and valid_through:
        quest["valid_through"] = valid_through
    applicant = posting.get("applicantLocationRequirements")
    if isinstance(applicant, dict) and applicant.get("name"):
        quest["applicant_country"] = str(applicant["name"])
    age_min, age_max = _extract_ages(low)
    if age_min is not None:
        quest["age_min"] = age_min
    if age_max is not None:
        quest["age_max"] = age_max
    if _NON_UNION_RE.search(low):
        quest["union"] = "non-union"
    if quest:
        row["quest"] = quest

    return row


def _fetch_role(url: str) -> dict | None:
    """Fetch one role page and map its JobPosting; None on any failure."""
    html = _get_html(url)
    if not html:
        return None
    posting = _find_jobposting(html)
    if posting is None:
        logger.debug("Casting Networks: no JobPosting block at %s", url)
        return None
    return _normalize_posting(posting, url)


@register_scraper(
    name="castingnetworks",
    display_name="Casting Networks",
    url="https://www.castingnetworks.com",
    description="Public casting calls from Casting Networks role pages",
    category="quest",
    # open calls page shifts daily
    refresh_hours=24,
    allowed_url_hosts=("castingnetworks.com",),
    enabled_by_default=False,
    vertical="camera",
)
def search_castingnetworks(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch public casting calls from Casting Networks.

    ``roles`` is ignored on purpose: career role keywords do not map onto
    casting-call titles, and this quest source is explicitly invoked only.
    One listing fetch yields the role deep links; each role page is then
    fetched for its JobPosting block. Any failure degrades to the rows
    collected so far.
    """
    logger.info("Fetching casting calls from Casting Networks...")
    listing_html = _get_html(_LISTING_URL)
    if not listing_html:
        return []
    role_urls = _listing_role_urls(listing_html)[:max_results]
    if not role_urls:
        logger.info("Casting Networks: no casting calls on the public listing")
        return []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(role_urls), _MAX_WORKERS)) as pool:
        futures = {pool.submit(_fetch_role, url): url for url in role_urls}
        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception as exc:
                logger.warning(
                    "Casting Networks role %s failed: %s", futures[future], exc,
                )
                continue
            if row is not None:
                results.append(row)

    # as_completed scrambles order; restore the listing's newest-first order.
    order = {url.rstrip("/"): i for i, url in enumerate(role_urls)}
    results.sort(key=lambda r: order.get(r["url"].rstrip("/"), len(order)))
    logger.info("Casting Networks: found %d casting calls", len(results))
    return results
