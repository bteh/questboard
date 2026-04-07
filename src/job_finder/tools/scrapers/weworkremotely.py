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

_WWR_CATEGORIES = {
    "programming": "remote-programming-jobs",
    "data": "remote-programming-jobs",
    "devops": "remote-devops-sysadmin-jobs",
    "management": "remote-management-finance-jobs",
    "all": "remote-jobs",
}


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
    **kwargs,
) -> list[dict]:
    """Fetch remote jobs from We Work Remotely RSS feeds."""
    logger.info("Fetching jobs from We Work Remotely RSS...")

    cats = categories or ["programming", "devops", "management", "all"]
    all_items: list[dict] = []

    for cat in cats:
        slug = _WWR_CATEGORIES.get(cat, cat)
        url = f"https://weworkremotely.com/categories/{slug}.rss"
        try:
            resp = requests.get(url, headers={
                "User-Agent": _HEADERS["User-Agent"],
                "Accept": "application/rss+xml,application/xml,text/xml",
            }, timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("WWR RSS fetch failed for %s: %s", cat, e)
            continue

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            if cat not in _SEEN_PARSE_FAILURES:
                _SEEN_PARSE_FAILURES.add(cat)
                logger.warning("WWR RSS parse failed for %s: %s", cat, e)
            else:
                logger.debug("WWR RSS parse failed for %s: %s", cat, e)
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

            if not _match_roles(title, roles):
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
