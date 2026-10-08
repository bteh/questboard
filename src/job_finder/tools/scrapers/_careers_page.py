"""Site shapes for a shop's own careers page. Every page-reading rule lives here.

A watched page (scrapers/watched_pages.py) goes through three readers, most
structured first:

1. ``find_ats_board``: the page links or embeds a hosted job board
   (Greenhouse, Lever, Ashby, Workable). The existing ATS fetchers read
   that board's API instead of this page.
2. ``jobposting_rows``: schema.org JobPosting JSON-LD in the page.
3. ``listing_rows``: known HTML listing shapes, one rule per shape.

Each rule names the real site that motivated it, and tests/test_careers_page.py
pins each one against a saved copy of that site. When this file collects
about a dozen listing rules, stop adding shapes and propose a principled
reader instead.

Pure: no network, no database.
"""

from __future__ import annotations

import html as _html
import json
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

# --- 1. hosted job boards ----------------------------------------------------

# Board hosts as they appear in hrefs, iframe srcs, and embed scripts. Same
# hosts the company watchlist accepts (backend watchlist_service), plus
# Workable, whose fetcher already exists in scrapers/workable.py.
_ATS_LINK_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(
        r"(?:boards|job-boards)\.greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)",
        re.IGNORECASE,
    )),
    ("greenhouse", re.compile(
        r"(?:boards|job-boards)\.greenhouse\.io/(?!embed\b)([A-Za-z0-9_-]+)", re.IGNORECASE,
    )),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)", re.IGNORECASE)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.IGNORECASE)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.IGNORECASE)),
)
_ATS_SLUG_BLOCKLIST = {"embed", "api", "v1", "j", "jobs", "careers"}


def find_ats_board(html: str) -> tuple[str, str] | None:
    """(ats, board slug) when the page links or embeds a hosted job board."""
    for ats, pattern in _ATS_LINK_RES:
        for match in pattern.finditer(html or ""):
            slug = match.group(1).strip().strip(".").lower()
            if slug and slug not in _ATS_SLUG_BLOCKLIST:
                return ats, slug
    return None


# --- shared field readers ----------------------------------------------------

_PERIOD_WORDS = {
    "hour": "hourly", "hr": "hourly", "hourly": "hourly",
    "day": "daily", "daily": "daily",
    "week": "weekly", "wk": "weekly", "weekly": "weekly",
    "month": "monthly", "mo": "monthly", "monthly": "monthly",
    "year": "yearly", "yr": "yearly", "annum": "yearly", "annual": "yearly",
    "annually": "yearly", "yearly": "yearly",
}

# ELOREA (Smoothie job board on Shopify): "22 - 25 usd / hour"
_PAY_TEXT_RE = re.compile(
    r"\$?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:(?:-|–|—|to)\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d+)?))?"
    r"\s*(?:usd|dollars)?\s*(?:/|per|an|a)\s*(hour|hr|day|week|wk|month|mo|year|yr|annum)\b",
    re.IGNORECASE,
)


def parse_pay_text(text: str) -> dict | None:
    """Stated pay as {salary_min, salary_max, salary_period}, or None."""
    match = _PAY_TEXT_RE.search(text or "")
    if not match:
        return None
    lo = float(match.group(1).replace(",", ""))
    hi = float(match.group(2).replace(",", "")) if match.group(2) else lo
    return {
        "salary_min": lo,
        "salary_max": hi,
        "salary_period": _PERIOD_WORDS[match.group(3).lower()],
        "salary_currency": "USD",
    }


def employment_type(value: Any) -> str:
    """'parttime', 'fulltime', or '' from a stated job type.

    ELOREA states it twice per card: job-type="PART_TIME" and "Part time".
    """
    if isinstance(value, (list, tuple)):
        kinds = {employment_type(v) for v in value} - {""}
        if "parttime" in kinds:
            return "parttime"
        return "fulltime" if "fulltime" in kinds else ""
    text = re.sub(r"[\s_-]+", "", str(value or "")).lower()
    if "parttime" in text or text in {"temporary", "perdiem", "seasonal"}:
        return "parttime"
    if "fulltime" in text:
        return "fulltime"
    return ""


def shop_name(html: str, page_url: str) -> str:
    """The shop's own name: og:site_name, then a JSON-LD Organization, then
    the <title> tail, then the host. ELOREA sets og:site_name="ELOREA"."""
    soup = BeautifulSoup(html or "", "html.parser")
    meta = soup.find("meta", attrs={"property": "og:site_name"})
    if meta and str(meta.get("content") or "").strip():
        return str(meta["content"]).strip()
    for node in _jsonld_nodes(soup):
        if _has_type(node, "Organization") and str(node.get("name") or "").strip():
            return str(node["name"]).strip()
    if soup.title and soup.title.string:
        parts = re.split(r"\s[|–—-]\s", soup.title.string.strip())
        if len(parts) > 1 and parts[-1].strip():
            return parts[-1].strip()
    host = (urlsplit(page_url).hostname or "").removeprefix("www.")
    return host.split(".")[0].capitalize() if host else ""


# --- 2. schema.org JobPosting ------------------------------------------------


def _jsonld_nodes(soup: BeautifulSoup) -> list[dict]:
    nodes: list[dict] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw, strict=False)
        except (json.JSONDecodeError, ValueError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                nodes.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
    return nodes


def _has_type(node: dict, wanted: str) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return any(str(k or "").lower() == wanted.lower() for k in kinds)


def _plain_text(value: Any) -> str:
    """JSON-LD description as plain text. ELOREA's is HTML escaped twice
    ("&lt;p&gt;..."), so unescape until stable before stripping tags."""
    text = str(value or "")
    for _ in range(3):
        unescaped = _html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def _place_text(location: Any) -> str:
    if isinstance(location, list):
        return "; ".join(p for p in (_place_text(item) for item in location) if p)
    if isinstance(location, str):
        return location.strip()
    if not isinstance(location, dict):
        return ""
    address = location.get("address", location)
    if isinstance(address, str):
        return address.strip()
    if isinstance(address, dict):
        parts = [
            str(address.get(key) or "").strip()
            for key in ("addressLocality", "addressRegion")
        ]
        return ", ".join(p for p in parts if p) or str(address.get("streetAddress") or "").strip()
    return ""


def _salary(base: Any) -> dict | None:
    if not isinstance(base, dict):
        return None
    value = base.get("value", base)
    if not isinstance(value, dict):
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return None
        value = {"value": amount, "unitText": base.get("unitText", "")}
    lo = value.get("minValue", value.get("value"))
    hi = value.get("maxValue", lo)
    try:
        lo_f = float(lo) if lo is not None else None
        hi_f = float(hi) if hi is not None else lo_f
    except (TypeError, ValueError):
        return None
    if lo_f is None:
        return None
    unit = str(value.get("unitText") or base.get("unitText") or "").strip().lower()
    return {
        "salary_min": lo_f,
        "salary_max": hi_f,
        "salary_period": _PERIOD_WORDS.get(unit, ""),
        "salary_currency": str(base.get("currency") or "USD").upper(),
    }


def jobposting_rows(html: str, page_url: str) -> list[dict]:
    """One row per schema.org JobPosting on the page (ELOREA detail pages)."""
    soup = BeautifulSoup(html or "", "html.parser")
    rows: list[dict] = []
    for node in _jsonld_nodes(soup):
        if not _has_type(node, "JobPosting"):
            continue
        title = str(node.get("title") or "").strip()
        if not title:
            continue
        org = node.get("hiringOrganization")
        row: dict = {
            "title": title,
            "company": str(org.get("name") or "").strip() if isinstance(org, dict) else "",
            "location": _place_text(node.get("jobLocation")),
            "url": urljoin(page_url, str(node.get("url") or "")) if node.get("url") else page_url,
            "employment": employment_type(node.get("employmentType")),
            "description": _plain_text(node.get("description")),
            "is_remote": str(node.get("jobLocationType") or "").upper() == "TELECOMMUTE",
        }
        posted = str(node.get("datePosted") or "").strip()
        if posted:
            row["date_posted"] = posted
        pay = _salary(node.get("baseSalary"))
        if pay:
            row.update(pay)
        rows.append(row)
    return rows


# --- 3. HTML listing shapes --------------------------------------------------


def _smoothie_cards(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """Smoothie (smooth.careers) job board embedded in a Shopify page.

    ELOREA, elorea.com/pages/career-opportunities, Oct 8 2026: each opening
    is <a href="/pages/<slug>"><li class="smoothie-job-listing-card"
    location=... job-type="PART_TIME"> with an <h3> title and detail spans
    titled "Career location", "Compensation", and "Job type".
    """
    rows: list[dict] = []
    for card in soup.select("li.smoothie-job-listing-card"):
        heading = card.find("h3")
        title = heading.get_text(" ", strip=True) if heading else ""
        link = card.find_parent("a") or card.find("a")
        href = str(link.get("href") or "") if link else ""
        if not title or not href:
            continue
        details = {
            str(span.get("title") or "").strip().lower(): span.get_text(" ", strip=True)
            for span in card.select("span.detail")
        }
        row: dict = {
            "title": title,
            "company": "",
            "location": str(card.get("location") or details.get("career location") or "").strip(),
            "url": urljoin(page_url, href),
            "employment": employment_type(card.get("job-type") or details.get("job type")),
            "description": "",
            "is_remote": False,
        }
        pay = parse_pay_text(details.get("compensation", ""))
        if pay:
            row.update(pay)
        rows.append(row)
    return rows


_LISTING_RULES = (_smoothie_cards,)


def listing_rows(html: str, page_url: str) -> list[dict]:
    """Rows from the first known listing shape that finds any."""
    soup = BeautifulSoup(html or "", "html.parser")
    for rule in _LISTING_RULES:
        rows = rule(soup, page_url)
        if rows:
            return rows
    return []


def read_page(html: str, page_url: str) -> list[dict]:
    """JobPosting JSON-LD when the page has it, else the listing shapes."""
    return jobposting_rows(html, page_url) or listing_rows(html, page_url)
