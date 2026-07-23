"""We Work Remotely — Remote jobs via RSS feed."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT, _match_roles, _strip_html

logger = logging.getLogger(__name__)
_SEEN_PARSE_FAILURES: set[str] = set()

# WWR reorganized its RSS surface (verified by live probe, 2026-07-22):
# - "remote-programming-jobs" no longer serves the programming category
#   (the old slug now returns a generic latest-25 mixed feed);
#   programming split into full-stack / back-end / front-end feeds.
# - "remote-management-finance-jobs" was renamed with an "and"
#   ("remote-management-and-finance-jobs"); the old slug 301s with an
#   EMPTY body and NO Location header, which raise_for_status() does not
#   catch, so the run just silently parsed zero bytes.
# - The all-jobs feed moved OUT of /categories/ to /remote-jobs.rss.
# WWR has no dedicated data category; data roles post under programming.
_WWR_SITE_FEED = "https://weworkremotely.com/remote-jobs.rss"

_WWR_CATEGORIES: dict[str, tuple[str, ...]] = {
    "programming": (
        "remote-full-stack-programming-jobs",
        "remote-back-end-programming-jobs",
        "remote-front-end-programming-jobs",
    ),
    "data": (
        "remote-full-stack-programming-jobs",
        "remote-back-end-programming-jobs",
    ),
    "devops": ("remote-devops-sysadmin-jobs",),
    "management": ("remote-management-and-finance-jobs",),
}


def _feed_urls(cats: list[str]) -> list[str]:
    """Resolve category names to a deduplicated, ordered list of feed URLs.

    "all" maps to the site-wide feed; unknown names are treated as literal
    category slugs so callers can pass a raw WWR slug directly.
    """
    urls: list[str] = []
    for cat in cats:
        if cat == "all":
            urls.append(_WWR_SITE_FEED)
            continue
        for slug in _WWR_CATEGORIES.get(cat, (cat,)):
            urls.append(f"https://weworkremotely.com/categories/{slug}.rss")
    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


@register_scraper(
    name="weworkremotely",
    display_name="We Work Remotely",
    url="https://weworkremotely.com",
    description="Remote jobs via RSS feeds",
    category="remote",
)
def search_weworkremotely(
    roles: list[str] | None = None,
    max_results: int = 50,
    categories: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch remote jobs from We Work Remotely RSS feeds."""
    logger.info("Fetching jobs from We Work Remotely RSS...")

    cats = categories or ["programming", "devops", "management", "all"]
    all_items: list[dict] = []

    for url in _feed_urls(cats):
        try:
            resp = requests.get(url, headers={
                "User-Agent": _HEADERS["User-Agent"],
                "Accept": "application/rss+xml,application/xml,text/xml",
            }, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("WWR RSS fetch failed for %s: %s", url, e)
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            # A retired slug 301s with an empty body (no Location header),
            # which raise_for_status() passes. The ParseError here is the
            # only signal that a feed URL has died. Warn once per URL.
            if url not in _SEEN_PARSE_FAILURES:
                _SEEN_PARSE_FAILURES.add(url)
                logger.warning("WWR RSS parse failed for %s: %s", url, e)
            else:
                logger.debug("WWR RSS parse failed for %s: %s", url, e)
            continue

        for item in root.iter("item"):
            raw_title = item.findtext("title", "")
            parts = raw_title.split(":", 1)
            if len(parts) == 2:
                company = parts[0].strip()
                title = parts[1].strip()
            else:
                company = ""
                title = raw_title

            loc_match = re.search(r"\(([^)]+)\)\s*$", title)
            region = item.findtext("region", "")
            if loc_match:
                region = loc_match.group(1)
                title = title[: loc_match.start()].strip()

            if not _match_roles(title, roles, match_mode=match_mode, include_founding=include_founding):
                continue

            desc_html = item.findtext("description", "")
            description = _strip_html(desc_html)

            all_items.append({
                "title": title,
                "company": company,
                "location": region or "Remote",
                "url": item.findtext("link", ""),
                "source": "weworkremotely",
                "description": description,
                "salary_min": None,
                "salary_max": None,
                "date_posted": item.findtext("pubDate", ""),
                "is_remote": True,
                "company_size": "",
            })

    # Deduplicate by URL
    seen: set[str] = set()
    results: list[dict] = []
    for job in all_items:
        u = job["url"]
        if u and u not in seen:
            seen.add(u)
            results.append(job)

    results = results[:max_results]

    logger.info("We Work Remotely: found %d matching jobs", len(results))
    return results
