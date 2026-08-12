"""Casting Networks - public casting calls from its server-rendered cards.

The source removed its JSON-LD listing in August 2026 and intermittently
returns 403 for the bare canonical URL. Its public casting-calls page still
server-renders mobile role cards with role/project names, stated rate,
location, ages, union, description, due date, and deep link. Questboard uses
that public HTML and a same-page fallback path; the older JSON-LD path remains
as a compatibility fallback for cached or regionally different responses.

Quest vertical: "camera". Career role keywords do not map onto casting-call
titles, so ``roles`` is accepted for registry compatibility and ignored.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _strip_html

logger = logging.getLogger(__name__)

_LISTING_URL = "https://www.castingnetworks.com/casting-calls/"
_LISTING_FALLBACK_URL = "https://www.castingnetworks.com/casting-calls/backgrounds/"
_ROLE_PATH_MARKER = "/talent/project/"
_MAX_WORKERS = 6
_PAGE_TIMEOUT = 10

# The shared headers advertise JSON; these pages are HTML.
_HTML_HEADERS = {
    **_HEADERS,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

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

_CARD_MONEY_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_CARD_DUE_RE = re.compile(r"Due\s+Date:\s*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)


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


def _clean(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _card_pill(card, icon_name: str) -> str:
    """Text beside a named icon in one current server-rendered role card."""
    for image in card.select("small img[src]"):
        if icon_name in str(image.get("src") or "").lower():
            return _clean(image.find_next_sibling("span"))
    return ""


def _card_rows(html: str) -> list[dict]:
    """Current mobile casting-call cards to rows, in listing order."""
    rows: list[dict] = []
    seen: set[str] = set()
    for card in BeautifulSoup(html, "html.parser").select(
        "li.casting-calls-card-mobile"
    ):
        link = card.select_one(f'a[href*="{_ROLE_PATH_MARKER}"]')
        title_node = card.select_one("h3")
        title = _clean(title_node)
        href = str(link.get("href") or "").strip() if link else ""
        url = urljoin("https://www.castingnetworks.com", href)
        if not title or not href or url in seen:
            continue
        seen.add(url)

        project = _clean(title_node.find_next_sibling("p")) if title_node else ""
        description = ""
        for label in card.select("p.fw-bold"):
            if _clean(label).casefold() == "about this role":
                description = _clean(label.find_next_sibling("p"))
                break
        rate = _card_pill(card, "payment_cc")
        age = _card_pill(card, "birthday-cake")
        union = _card_pill(card, "union")
        location = _card_pill(card, "location_cc")
        card_box = card.select_one("div.card")

        quest: dict = {}
        if card_box is not None:
            if card_box.get("project-id"):
                quest["project_id"] = str(card_box["project-id"])
            if card_box.get("role-id"):
                quest["role_id"] = str(card_box["role-id"])
            if card_box.get("data-project-type"):
                quest["project_type"] = str(card_box["data-project-type"])
        if rate:
            quest["pay_note"] = rate
        if union:
            quest["union"] = union
        age_numbers = [int(value) for value in re.findall(r"\d{1,2}", age)]
        if age_numbers and 0 < age_numbers[0] < 100:
            quest["age_min"] = age_numbers[0]
            if len(age_numbers) > 1 and age_numbers[0] <= age_numbers[1] < 100:
                quest["age_max"] = age_numbers[1]

        due_match = _CARD_DUE_RE.search(_clean(card))
        due = ""
        if due_match:
            try:
                due = datetime.strptime(due_match.group(1), "%m/%d/%Y").date().isoformat()
            except ValueError:
                due = ""
        if due:
            quest["apply_by"] = due

        row: dict = {
            "title": title,
            "company": project or "Casting Networks",
            "location": location,
            "url": url,
            "source": "castingnetworks",
            "vertical": "camera",
            "description": description,
            "quest": quest,
        }
        if due:
            row["event_end"] = due
        amounts = [float(value.replace(",", "")) for value in _CARD_MONEY_RE.findall(rate)]
        if amounts:
            row["salary_min"] = min(amounts)
            row["salary_max"] = max(amounts)
            row["salary_period"] = "session"
            row["salary_source"] = "reported"
        low = f"{title}\n{description}".lower()
        if any(rx.search(low) for rx in _FIRST_QUEST_RES):
            row["first_quest_ok"] = True
        rows.append(row)
    return rows


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
        listing_html = _get_html(_LISTING_FALLBACK_URL)
    if not listing_html:
        return []

    card_rows = _card_rows(listing_html)
    if card_rows:
        rows = card_rows[:max_results]
        logger.info("Casting Networks: found %d casting calls from listing cards", len(rows))
        return rows

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
