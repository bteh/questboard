"""AuditionsFree - open casting calls via the public WordPress REST API.

AuditionsFree publishes open casting calls (film, TV, theater, reality,
commercials) as WordPress posts. The standard WP REST endpoint is open::

    GET https://www.auditionsfree.com/wp-json/wp/v2/posts?per_page=20&page=N

Each post carries ``title.rendered``, ``link`` (the deep link a user lands
on), ``date_gmt``, and ``content.rendered`` (the full call as HTML). Posts
are label-structured prose ("Location: Atlanta, GA", "PAY RATE: $100/8hrs",
"ages 9-14"), so this scraper extracts only explicitly labeled facts and
omits anything the post does not state outright. Casting pay commonly uses
the day-rate shorthand "$100/8hrs" (a flat amount for an N-hour day).

Quest vertical: "camera". Career role keywords do not map onto casting-call
titles, so the ``roles`` argument is accepted for registry compatibility and
deliberately ignored.
"""

from __future__ import annotations

import logging
import re
from html import unescape

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://www.auditionsfree.com/wp-json/wp/v2/posts"
_PAGE_SIZE = 20
_MAX_PAGES = 5

# Block-level closers and <br> become newlines so labeled lines survive the
# tag strip ("PAY RATE:" and its value often sit on adjacent <br> lines).
_BLOCK_BREAK_RE = re.compile(
    r"<\s*(?:br\s*/?|/p|/li|/h[1-6]|/div|/tr|/blockquote)[^>]*>", re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")

# Dash class used in age ranges and pay ranges: hyphen, en dash, em dash.
# Escapes on purpose: the copy rules ban literal em dashes in this file.
_DASH = "[-\u2013\u2014]"

_LOCATION_LABELS: tuple[str, ...] = ("filming location", "location")
_COMPANY_LABELS: tuple[str, ...] = (
    "producer/theatre company", "production company", "theatre company",
    "producer", "network",
)

_PAY_LABEL_RE = re.compile(r"\b(?:pay\s*rate|compensation|stipend|pay|rate)s?\s*:", re.IGNORECASE)
_MONEY_PART = r"\$\s*(\d[\d,]{0,9}(?:\.\d{1,2})?)"
# Casting day-rate shorthand: "$140/10 hrs", "$500/12" (flat rate, N-hour day).
_DAY_RATE_RE = re.compile(_MONEY_PART + r"\s*/\s*(\d{1,2})\s*(?:h(?:ou)?rs?\b)?")
_HOURLY_RE = re.compile(_MONEY_PART + r"\s*(?:/|\bper\s+|\bp/\s*)h(?:ours?|rs?)?\b", re.IGNORECASE)
_MONEY_RANGE_RE = re.compile(_MONEY_PART + rf"\s*(?:{_DASH}|to\s)\s*\$?\s*(\d[\d,]{{0,9}}(?:\.\d{{1,2}})?)")
_MONEY_RE = re.compile(_MONEY_PART)

_AGE_RANGE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\bages?\s*:?\s*(\d{{1,2}})\s*(?:{_DASH}|to\s)\s*(\d{{1,2}})\b"),
    re.compile(rf"\b(\d{{1,2}})\s*(?:{_DASH}|to\s)\s*(\d{{1,2}})\s*(?:years?|yrs?)\s*(?:of\s+age|old)\b"),
)
_AGE_MIN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d{1,2})\s*(?:years?|yrs?)\s*(?:of\s+age|old)\s*(?:\+|or\s+older|and\s+(?:up|older))"),
    re.compile(r"\bages?\s+(\d{1,2})\s*\+"),
    re.compile(r"\bat\s+least\s+(\d{1,2})\s+(?:years?|yrs?)\s*(?:of\s+age|old)\b"),
)

# Explicit beginner-open statements only; extras/background work is often
# beginner-open in practice, but we never claim it unless the post says so.
_FIRST_QUEST_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bno\s+(?:prior\s+|previous\s+|acting\s+|modeling\s+|professional\s+)?"
        r"experience\s+(?:is\s+)?(?:necessary|needed|required)\b"
    ),
    re.compile(r"\bexperience\s+(?:is\s+)?[^.\n]{0,40}?not\s+(?:necessary|needed|required)\b"),
)

_NON_UNION_RE = re.compile(r"\bnon[- ]?union\b")

_PAY_MIN = 5.0
_PAY_MAX = 25000.0


def _content_lines(html: str) -> list[str]:
    """Split rendered post HTML into clean text lines, one per block/<br>."""
    text = _BLOCK_BREAK_RE.sub("\n", html)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    lines: list[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def _labeled_value(lines: list[str], labels: tuple[str, ...]) -> str:
    """Value of the first ``Label: value`` line matching one of ``labels``.

    Handles the value sitting on the next line ("PAY RATE:" then "$100/8hrs"),
    but never steals a following line that is itself another label. Returns ""
    when no label is present, so absent facts stay absent.
    """
    for i, line in enumerate(lines):
        low = line.lower()
        for label in labels:
            if not low.startswith(label):
                continue
            m = re.match(r"\s*:\s*(.*)$", line[len(label):])
            if m is None:
                continue
            value = m.group(1).strip()
            if not value and i + 1 < len(lines) and not lines[i + 1].endswith(":"):
                value = lines[i + 1].strip()
            if value:
                return value[:90]
    return ""


def _money(num_str: str) -> float | None:
    """Parse a captured dollar amount, bounded to plausible casting pay."""
    try:
        val = float(num_str.replace(",", ""))
    except ValueError:
        return None
    return val if _PAY_MIN <= val <= _PAY_MAX else None


def _extract_pay(
    text: str,
) -> tuple[float | None, float | None, str | None, str, int | None]:
    """Pay stated after an explicit pay label, or all-None when absent.

    Returns ``(salary_min, salary_max, period, pay_text, session_hours)``.
    Only the window right after a "Pay Rate:" / "Rate:" / "Compensation:"
    label is scanned, so prize money, budgets, and body-text dollar figures
    never become pay. Multiple labeled rates in one post (multi-role casting
    notices) collapse to the stated min/max when their periods agree.
    """
    entries: list[tuple[float, float, str | None, int | None]] = []
    pay_text = ""
    for lm in _PAY_LABEL_RE.finditer(text):
        window = text[lm.end():lm.end() + 140]
        found: tuple[float, float, str | None, int | None] | None = None
        dm = _DAY_RATE_RE.search(window)
        if dm:
            val = _money(dm.group(1))
            if val is not None:
                found = (val, val, "daily", int(dm.group(2)))
        if found is None:
            hm = _HOURLY_RE.search(window)
            if hm:
                val = _money(hm.group(1))
                if val is not None:
                    found = (val, val, "hourly", None)
        if found is None:
            rm = _MONEY_RANGE_RE.search(window)
            if rm:
                lo, hi = _money(rm.group(1)), _money(rm.group(2))
                if lo is not None and hi is not None and lo <= hi:
                    found = (lo, hi, None, None)
        if found is None:
            sm = _MONEY_RE.search(window)
            if sm:
                val = _money(sm.group(1))
                if val is not None:
                    found = (val, val, None, None)
        if found is None:
            continue
        entries.append(found)
        if not pay_text:
            snippet = text[lm.start():lm.end() + 90].split("\n")
            pay_text = " ".join(s.strip() for s in snippet if s.strip())[:120]

    if not entries:
        return None, None, None, "", None
    periods = {e[2] for e in entries}
    if len(entries) == 1 or len(periods) == 1:
        lo = min(e[0] for e in entries)
        hi = max(e[1] for e in entries)
        period = entries[0][2]
        hours = entries[0][3] if len(entries) == 1 else None
        return lo, hi, period, pay_text, hours
    # Mixed periods across roles: keep only the first stated rate.
    lo, hi, period, hours = entries[0]
    return lo, hi, period, pay_text, hours


def _extract_ages(low: str) -> tuple[int | None, int | None]:
    """Stated age bounds ("ages 9-14", "21-65 years of age", "ages 18+")."""
    for rx in _AGE_RANGE_RES:
        m = rx.search(low)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b < 100:
                return a, b
    for rx in _AGE_MIN_RES:
        m = rx.search(low)
        if m:
            a = int(m.group(1))
            if 0 < a < 100:
                return a, None
    return None, None


def _first_quest_ok(low: str) -> bool:
    """True only when the post explicitly says experience is not required."""
    return any(rx.search(low) for rx in _FIRST_QUEST_RES)


def _normalize_post(post: object) -> dict | None:
    """Map one WP post object to a quest row, or None on a bad/partial post."""
    if not isinstance(post, dict):
        return None
    title_field = post.get("title")
    title_html = title_field.get("rendered", "") if isinstance(title_field, dict) else ""
    title = _strip_html(title_html or "")
    url = post.get("link") or ""
    if not title or not url:
        return None

    content_field = post.get("content")
    content_html = content_field.get("rendered", "") if isinstance(content_field, dict) else ""
    content_html = content_html or ""
    lines = _content_lines(content_html)
    text = "\n".join(lines)
    low = text.lower()

    row: dict = {
        "title": title,
        "company": _labeled_value(lines, _COMPANY_LABELS),
        "location": _labeled_value(lines, _LOCATION_LABELS),
        "url": url,
        "source": "auditionsfree",
        "vertical": "camera",
        "description": _strip_html(content_html),
    }

    # WP always stamps the publish date; date_gmt is UTC.
    date_posted = post.get("date_gmt") or post.get("date") or ""
    if date_posted:
        row["date_posted"] = date_posted

    lo, hi, period, pay_text, hours = _extract_pay(text)
    if lo is not None or hi is not None:
        row["salary_min"] = lo
        row["salary_max"] = hi
        if period:
            row["salary_period"] = period
        row["salary_source"] = "reported"

    if _first_quest_ok(low):
        row["first_quest_ok"] = True

    quest: dict = {}
    age_min, age_max = _extract_ages(low)
    if age_min is not None:
        quest["age_min"] = age_min
    if age_max is not None:
        quest["age_max"] = age_max
    if hours is not None:
        quest["session_hours"] = hours
    if pay_text:
        quest["pay_text"] = pay_text
    if _NON_UNION_RE.search(low):
        quest["union"] = "non-union"
    if quest:
        row["quest"] = quest

    return row


@register_scraper(
    name="auditionsfree",
    display_name="AuditionsFree",
    url="https://www.auditionsfree.com",
    description="Open casting calls for film, TV, theater, and reality shows",
    category="quest",
    # calls post daily
    refresh_hours=24,
    enabled_by_default=False,
    vertical="camera",
)
def search_auditionsfree(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch open casting calls from the AuditionsFree WordPress REST API.

    ``roles`` is ignored on purpose: career role keywords do not map onto
    casting-call titles, and this quest source is explicitly invoked only.
    Paginates newest-first until ``max_results`` or ``_MAX_PAGES``; any
    failure degrades to the rows collected so far.
    """
    logger.info("Fetching casting calls from AuditionsFree...")
    results: list[dict] = []
    seen_urls: set[str] = set()
    pages = max(1, min(_MAX_PAGES, -(-max_results // _PAGE_SIZE)))

    for page in range(1, pages + 1):
        # WP returns 400 for a page past the end; quiet, it just ends the walk.
        data = _get_json(
            _API_URL,
            params={"per_page": _PAGE_SIZE, "page": page},
            quiet_statuses={400},
        )
        if not isinstance(data, list) or not data:
            break
        for post in data:
            if len(results) >= max_results:
                break
            row = _normalize_post(post)
            if row is None or row["url"] in seen_urls:
                continue
            seen_urls.add(row["url"])
            results.append(row)
        if len(results) >= max_results or len(data) < _PAGE_SIZE:
            break

    logger.info("AuditionsFree: found %d casting calls", len(results))
    return results
