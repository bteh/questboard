"""SBIR.gov open topics (pitch kind): federal R&D funding for US small businesses.

SBIR.gov lists every open SBIR/STTR topic on a server-rendered Drupal
search page; plain requests get a 200 and robots.txt does not disallow
/topics (live-verified 2026-07-12, ~46 open topics, 10 per page)::

    GET https://www.sbir.gov/topics?keywords=&status=Open&page=N   (page=0..)

Each listing block carries the topic title, an Open status chip, the
release/open/close dates, the funding agency's seal, a teaser
description, and SBIR/STTR + phase tags. The detail page
``/topics/{id}`` adds the Funding Agency by name (the counterparty),
topic and solicitation numbers, the due-date schedule, the full
description, and the "View Official Solicitation" link (often
simpler.grants.gov or dodsbirsttr.mil). DOD topics state the agency as
two lines, department then branch ("DOW" / "MDA"); both join into the
counterparty. Rows anchor at the sbir.gov topic page, which is public
and stable; the official link rides in ``quest.official_solicitation``
and in the description.

The official JSON API (api.www.sbir.gov) was down for maintenance at
build time (403/429, "The SBIR Public API is not available at this
time"). It is the upgrade path when it returns: offset pagination via
``start``/``rows`` params per their docs.

Awards are phase-based, so amounts render only when the page states
them: "budgets ... up to $X" maps to a salary_max ceiling, never a
floor; anything else emits no salary keys. The close date becomes the
quest's apply_by and rows past their deadline are dropped. Eligibility
is US small businesses by law, which is exactly the pitch lane's
audience.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://www.sbir.gov"
_LIST_URL = _BASE + "/topics?keywords=&status=Open&page={page}"
_MAX_PAGES = 10  # ~46 open topics live; a runaway pager stops here

_US_DATE = r"[A-Za-z]+ \d{1,2}, \d{4}"
_RELEASE_RE = re.compile(rf"Release Date:\s*({_US_DATE})")
_CLOSE_RE = re.compile(rf"Close Date:\s*({_US_DATE})")
_PROGRAM_TAGS = {"SBIR", "STTR"}
# "budgets ... up to $X" states a ceiling, never a floor
_CEILING_RE = re.compile(
    r"(?:award|budget|fund(?:ing)?)s?[^.$]{0,80}?up\s+to\s+\$([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_us_date(text: str | None):
    if not text:
        return None
    try:
        return datetime.strptime(_clean(text), "%B %d, %Y").date()
    except ValueError:
        return None


def _parse_award_ceiling(text: str) -> dict:
    """Salary keys only for a stated "up to $X" award ceiling, else {}."""
    amounts = [float(m.replace(",", "")) for m in _CEILING_RE.findall(text or "")]
    if not amounts:
        return {}
    return {"salary_max": max(amounts), "salary_source": "reported"}


def _parse_listing(html: str) -> list[dict]:
    """One listing page to raw topic dicts (title/url/status/dates/agency/...)."""
    soup = BeautifulSoup(html, "html.parser")
    hits = soup.find("div", id="search-results-hits")
    if hits is None:
        return []
    topics: list[dict] = []
    for h3 in hits.find_all("h3", recursive=False):
        link = h3.find("a")
        if link is None or not link.get("href"):
            continue
        title = _clean(link.get_text(" ", strip=True))
        if not title:
            continue
        topic: dict = {"title": title, "url": urljoin(_BASE, link["href"])}

        meta_p = h3.find_next_sibling("p")
        if meta_p is not None:
            chip = meta_p.find("span")
            topic["status"] = _clean(chip.get_text()) if chip else ""
            meta_text = _clean(meta_p.get_text(" ", strip=True))
            release = _RELEASE_RE.search(meta_text)
            close = _CLOSE_RE.search(meta_text)
            topic["release"] = release.group(1) if release else ""
            topic["close"] = close.group(1) if close else ""

        body = meta_p.find_next_sibling("div") if meta_p is not None else None
        if body is not None:
            seal = body.find("img", alt=re.compile(r"Seal of the Agency"))
            if seal:
                topic["agency"] = _clean(seal["alt"].split(":", 1)[-1])
            teaser = body.find("p", class_="measure-6")
            if teaser:
                topic["description"] = _clean(teaser.get_text(" ", strip=True))
            topic["tags"] = [
                _clean(p.get_text())
                for p in body.find_all("p", class_="bg-base-dark")
            ]
        topics.append(topic)
    return topics


def _fetch_listing(page: int) -> list[dict]:
    url = _LIST_URL.format(page=page)
    try:
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("SBIR listing page %d fetch failed: %s", page, exc)
        return []
    return _parse_listing(resp.text)


def _parse_detail(html: str) -> dict:
    """One topic detail page to enrichment fields; missing pieces just absent."""
    soup = BeautifulSoup(html, "html.parser")
    info: dict = {}

    agency_h3 = soup.find(
        lambda tag: tag.name == "h3" and "Funding Agency" in tag.get_text()
    )
    if agency_h3 is not None:
        # DOD topics state two lines: department ("DOW") then branch ("MDA")
        parts = [_clean(p.get_text()) for p in agency_h3.find_next_siblings("p")]
        parts = [p for p in parts if p]
        if parts:
            info["agency"] = " / ".join(parts)

    for p in soup.find_all("p"):
        strong = p.find("strong")
        if strong is None:
            continue
        label = _clean(strong.get_text()).rstrip(":")
        strong.extract()
        value = _clean(p.get_text(" ", strip=True))
        if label == "Topic Number" and value:
            info["topic_number"] = value
        elif label == "Solicitation Number" and value:
            info["solicitation_number"] = value
        elif label == "Close Date" and value:
            info["close"] = value
        elif label == "Due Date(s)" and value:
            info["due_dates"] = value

    official = soup.find(
        lambda tag: tag.name == "a" and "View Official Solicitation" in tag.get_text()
    )
    if official is not None and official.get("href"):
        info["official_url"] = official["href"].strip()

    desc = soup.find("div", class_="pre-form-wrapped")
    if desc is not None:
        info["description"] = desc.get_text("\n", strip=True)
    return info


def _fetch_detail(url: str) -> dict:
    try:
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("SBIR detail %s fetch failed: %s", url, exc)
        return {}
    return _parse_detail(resp.text)


def _normalize_topic(topic: dict, today) -> dict | None:
    """One raw listing topic to a pitch-kind quest row, or None to skip."""
    status = topic.get("status", "")
    if status and status.lower() != "open":
        return None
    close = _parse_us_date(topic.get("close"))
    if close is not None and close < today:
        return None

    row: dict = {
        "title": topic["title"],
        "company": topic.get("agency") or "SBIR.gov",
        "location": "United States",
        "url": topic["url"],
        "source": "sbir",
        "vertical": "pitch",
        "description": topic.get("description", ""),
    }
    release = _parse_us_date(topic.get("release"))
    if release is not None:
        row["date_posted"] = release.isoformat()

    quest: dict = {}
    if close is not None:
        quest["apply_by"] = close.isoformat()
    tags = topic.get("tags") or []
    programs = [t for t in tags if t in _PROGRAM_TAGS]
    phases = [t for t in tags if t not in _PROGRAM_TAGS]
    if programs:
        quest["program"] = " / ".join(programs)
    if phases:
        quest["phase"] = phases[0]
    if quest:
        row["quest"] = quest
    return row


def _enrich_from_detail(row: dict, detail: dict) -> None:
    if not detail:
        return
    quest = row.setdefault("quest", {})
    if detail.get("agency"):
        row["company"] = detail["agency"]
    for key in ("topic_number", "solicitation_number", "due_dates"):
        if detail.get(key):
            quest[key] = detail[key]
    close = _parse_us_date(detail.get("close"))
    if close is not None:
        quest["apply_by"] = close.isoformat()
    # some listing teasers truncate to a single word ("Background...");
    # the detail's own description is the better summary
    full = _clean(detail.get("description", ""))
    if full:
        if len(full) > 400:
            full = full[:400].rsplit(" ", 1)[0] + "..."
        row["description"] = full
    if detail.get("official_url"):
        quest["official_solicitation"] = detail["official_url"]
        row["description"] = (
            f"{row['description']} Official solicitation: {detail['official_url']}".strip()
        )
    row.update(_parse_award_ceiling(detail.get("description", "")))


@register_scraper(
    name="sbir",
    display_name="SBIR.gov",
    url="https://www.sbir.gov",
    description="Open SBIR/STTR federal R&D funding topics for US small businesses, with deadlines",
    category="pitch",
    kind="pitch",
    # the paginated open set IS the source's entire current set
    full_snapshot=True,
    # topics turn over on solicitation cycles; one polite sweep a day
    refresh_hours=24,
    allowed_url_hosts=("sbir.gov",),
    enabled_by_default=False,
    # off-ICP for the builder-funding lane (federal R&D topics for US small
    # businesses, not funding for young founders/students); kept as code
    research_only=True,
)
def search_sbir(
    roles: list[str] | None = None,
    max_results: int = 25,
    **kwargs,
) -> list[dict]:
    """Fetch open SBIR/STTR topics, enriched from each topic's detail page.

    ``roles`` is ignored on purpose: funding topics are not career titles.
    Detail fetches are capped at ``max_results`` with a 1s sleep between
    requests to stay polite.
    """
    logger.info("Fetching open topics from SBIR.gov...")
    today = _utcnow().date()

    results: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(_MAX_PAGES):
        if len(results) >= max_results:
            break
        if page:
            time.sleep(1.0)
        new_topics = 0
        for topic in _fetch_listing(page):
            if topic["url"] in seen_urls:
                continue
            seen_urls.add(topic["url"])
            new_topics += 1
            if len(results) >= max_results:
                continue
            row = _normalize_topic(topic, today)
            if row is not None:
                results.append(row)
        if not new_topics:
            break

    for i, row in enumerate(results):
        if i:
            time.sleep(1.0)
        _enrich_from_detail(row, _fetch_detail(row["url"]))

    logger.info("SBIR.gov: %d open topics", len(results))
    return results
