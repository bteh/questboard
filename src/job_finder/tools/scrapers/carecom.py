"""Care.com (lookafter kind): childcare, pet care, and special-needs sits.

Care.com exposes its full public job set through a sitemap index
(live-verified 2026-07-10)::

    GET https://www.care.com/alpha-omega-jobs.xml
        -> alpha-omega-jobs_auto_1.xml.gz   (~34k job URLs)
        -> alpha-omega-jobs_manual_1.xml.gz (~2.7k)

Job URLs are ``/job/{vertical}/{st}/{city}/{id}-{slug}`` with sequential
ids, so sorting by id desc surfaces the newest postings without a search
endpoint. Verticals childcare, petcare, and specialneeds feed this lane;
seniorcare and housekeeping are skipped. Each detail page embeds a
JSON-LD JobPosting whose ``baseSalary`` is the family's own posted
hourly range: pay renders only from that block (salary_source
"reported", salary_period "hourly"), never estimated from prose, and a
zero value means the poster left pay blank.

``hiringOrganization`` names the platform itself, so it never stands in
as counterparty; the ``identifier`` PropertyValue carries the poster's
name and rows credit "Becca B via Care.com" (fallback "Posted family
via Care.com"). Rows whose ``validThrough`` has passed are dropped;
otherwise it becomes the quest's apply_by. robots.txt sets
Crawl-delay 1, so detail fetches sleep 1.5s apart and each run reads at
most ~40 pages.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import time
from datetime import datetime, timezone

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _parse_posted_date,
    _strip_html,
)

logger = logging.getLogger(__name__)

_SITEMAP_INDEX_URL = "https://www.care.com/alpha-omega-jobs.xml"
_SOURCE = "carecom"
_PLATFORM = "Care.com"

_KEPT_VERTICALS = frozenset({"childcare", "petcare", "specialneeds"})

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_JOB_URL_RE = re.compile(
    r"https?://(?:www\.)?care\.com/job/([a-z]+)/[a-z]{2}/[^/<]+/(\d+)-"
)
_LDJSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# The shared _HEADERS advertise Accept: application/json; this source
# serves XML sitemaps and HTML pages.
_XML_ACCEPT = "application/xml, text/xml;q=0.9, */*;q=0.8"
_HTML_ACCEPT = "text/html, application/xhtml+xml;q=0.9, */*;q=0.8"

# robots.txt Crawl-delay is 1; stay comfortably above it.
_CRAWL_DELAY_S = 1.5
# One slow detail page must not stall the sweep.
_DETAIL_TIMEOUT = 10
# Politeness ceiling per run, independent of max_results.
_DETAIL_FETCH_CAP = 40


def _fetch_text(url: str, accept: str, timeout: float) -> str | None:
    """GET a URL as text, gunzipping .gz sitemap payloads; None on failure."""
    try:
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": accept}, timeout=timeout
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Care.com fetch failed (%s): %s", url, exc)
        return None
    body = resp.content
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError as exc:
            logger.warning("Care.com sitemap gunzip failed (%s): %s", url, exc)
            return None
    return body.decode("utf-8", errors="replace")


def _fetch_job_urls() -> list[str]:
    """All job URLs from the sitemap index's gz files; partial on failure."""
    index = _fetch_text(_SITEMAP_INDEX_URL, _XML_ACCEPT, _TIMEOUT)
    if not index:
        return []
    urls: list[str] = []
    for sitemap_url in _LOC_RE.findall(index):
        text = _fetch_text(sitemap_url, _XML_ACCEPT, _TIMEOUT)
        if text:
            urls.extend(_LOC_RE.findall(text))
    return urls


# Round-robin order across kept verticals. Pets lead so a high-volume
# childcare backlog can't crowd pet-care out of the per-run fetch cap
# (the whole point of the pets-first lane).
_VERTICAL_ORDER = ("petcare", "childcare", "specialneeds")


def _newest_first(urls: list[str]) -> list[str]:
    """Kept-vertical job URLs, deduped by id, newest first, round-robined across
    verticals so childcare volume can't starve pet-care within the fetch cap.
    Each vertical stays newest-first internally; pets take the first slot."""
    by_vertical: dict[str, dict[int, str]] = {}
    for url in urls:
        m = _JOB_URL_RE.match(url.strip())
        if not m or m.group(1) not in _KEPT_VERTICALS:
            continue
        by_vertical.setdefault(m.group(1), {}).setdefault(int(m.group(2)), url.strip())

    lanes = [
        [keyed[job_id] for job_id in sorted(keyed, reverse=True)]
        for vertical in _VERTICAL_ORDER
        if (keyed := by_vertical.get(vertical))
    ]
    out: list[str] = []
    for i in range(max((len(lane) for lane in lanes), default=0)):
        for lane in lanes:
            if i < len(lane):
                out.append(lane[i])
    return out


def _find_job_posting(html: str) -> dict | None:
    """The JSON-LD JobPosting node from a job page, or None."""
    for raw in _LDJSON_RE.findall(html):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "JobPosting":
                return node
    return None


def _company(posting: dict) -> str:
    """Poster credit; the platform never stands in as counterparty."""
    org = posting.get("hiringOrganization")
    name = str(org.get("name") or "").strip() if isinstance(org, dict) else ""
    if name.lower() in ("", _PLATFORM.lower()):
        ident = posting.get("identifier")
        name = str(ident.get("name") or "").strip() if isinstance(ident, dict) else ""
    return f"{name} via {_PLATFORM}" if name else f"Posted family via {_PLATFORM}"


def _ld_location(posting: dict) -> str:
    """'Locality, Region' from JSON-LD jobLocation, '' when absent."""
    place = posting.get("jobLocation")
    if isinstance(place, list):
        place = place[0] if place else None
    address = place.get("address") if isinstance(place, dict) else None
    if not isinstance(address, dict):
        return ""
    parts = [
        str(address.get(key) or "").strip()
        for key in ("addressLocality", "addressRegion")
    ]
    return ", ".join(p for p in parts if p)


def _ld_hourly_salary(posting: dict) -> dict:
    """Salary fields from JSON-LD baseSalary; {} unless a real hourly rate.

    Care.com emits value 0 when the poster left structured pay blank, so
    zero means "not stated" and produces no salary keys. Only unitText
    HOUR maps (the poster-set form); anything else stays unrendered.
    """
    base = posting.get("baseSalary")
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return {}
    if str(value.get("unitText") or "").upper() != "HOUR":
        return {}

    def _num(raw: object) -> float | None:
        try:
            num = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return num if num > 0 else None

    lo, hi = _num(value.get("minValue")), _num(value.get("maxValue"))
    if lo is None and hi is None:
        return {}
    out: dict = {"salary_period": "hourly", "salary_source": "reported"}
    if lo is not None:
        out["salary_min"] = lo
    if hi is not None:
        out["salary_max"] = hi
    return out


def _normalize_posting(posting: dict, url: str) -> dict | None:
    """One JSON-LD JobPosting to a lookafter-kind quest row, or None."""
    title = re.sub(r"\s+", " ", str(posting.get("title") or "")).strip()
    if not title:
        return None
    row: dict = {
        "title": title,
        "company": _company(posting),
        "location": _ld_location(posting),
        "url": url,
        "source": _SOURCE,
        "vertical": "lookafter",
        "description": _strip_html(str(posting.get("description") or "")),
    }
    date_posted = str(posting.get("datePosted") or "").strip()
    if date_posted:
        row["date_posted"] = date_posted
    row.update(_ld_hourly_salary(posting))
    valid_through = str(posting.get("validThrough") or "").strip()
    if valid_through:
        row["quest"] = {"apply_by": valid_through}
    return row


def _utcnow() -> datetime:
    """Wrapped so tests can freeze the clock."""
    return datetime.now(timezone.utc)


def _is_expired(row: dict) -> bool:
    """True when the stated apply-by deadline has already passed.

    The sitemaps keep filled/closed postings around for a while; serving
    those as live quests would be dishonest. Rows without a stated
    deadline are kept.
    """
    deadline = _parse_posted_date((row.get("quest") or {}).get("apply_by"))
    return deadline is not None and deadline < _utcnow()


@register_scraper(
    name="carecom",
    display_name="Care.com",
    url="https://www.care.com",
    description="Childcare, pet care, and special-needs sits with the family's own posted hourly rate",
    category="lookafter",
    kind="lookafter",
    # sits get filled fast; an unconfirmed row shouldn't linger
    stale_after_days=10,
    # sitemaps regenerate daily; one polite sweep matches that rhythm
    refresh_hours=24,
    allowed_url_hosts=("care.com",),
    enabled_by_default=False,
)
def search_carecom(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch the newest care postings from the Care.com job sitemaps.

    ``roles`` is ignored on purpose: sits are not career titles. Detail
    fetches sleep 1.5s apart (robots Crawl-delay 1) and are capped at
    ~40 per run regardless of ``max_results``.
    """
    logger.info("Fetching care postings from Care.com sitemaps...")
    candidates = _newest_first(_fetch_job_urls())

    results: list[dict] = []
    fetched = 0
    for url in candidates:
        if len(results) >= max_results or fetched >= _DETAIL_FETCH_CAP:
            break
        if fetched:
            time.sleep(_CRAWL_DELAY_S)
        fetched += 1
        html = _fetch_text(url, _HTML_ACCEPT, _DETAIL_TIMEOUT)
        if not html:
            continue
        posting = _find_job_posting(html)
        if not posting:
            continue
        row = _normalize_posting(posting, url)
        if row is None or _is_expired(row):
            continue
        results.append(row)

    logger.info("Care.com: %d postings", len(results))
    return results
