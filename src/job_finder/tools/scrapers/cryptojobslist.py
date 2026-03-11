"""CryptoJobsList — Crypto/Web3/Blockchain jobs via JSON API with RSS fallback."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _get_json,
    _match_roles_crypto,
    _parse_salary,
    _strip_html,
)

logger = logging.getLogger(__name__)


@register_scraper(
    name="cryptojobslist",
    display_name="CryptoJobsList",
    url="https://cryptojobslist.com",
    description="Crypto, Web3 and blockchain jobs",
    category="crypto",
    enabled_by_default=False,
)
def search_cryptojobslist(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch crypto/web3 jobs from CryptoJobsList."""
    logger.info("Fetching jobs from CryptoJobsList...")

    data = _get_json(
        "https://cryptojobslist.com/api/jobs",
        params={"limit": max(max_results * 3, 100)},
    )

    if data and isinstance(data, dict) and data.get("jobs"):
        return _parse_cryptojobs_json(data["jobs"], roles, max_results)

    if data and isinstance(data, list):
        return _parse_cryptojobs_json(data, roles, max_results)

    logger.info("CryptoJobsList JSON API failed, trying RSS...")
    return _parse_cryptojobs_rss(roles, max_results)


def _parse_cryptojobs_json(
    jobs: list[dict],
    roles: list[str] | None,
    max_results: int,
) -> list[dict]:
    """Parse CryptoJobsList JSON response."""
    results: list[dict] = []
    for job in jobs:
        title = job.get("title", "") or job.get("position", "")
        if not title:
            continue

        if roles and not _match_roles_crypto(title, roles):
            continue

        sal_min, sal_max = _parse_salary(job.get("salary", ""))

        location = job.get("location", "")
        is_remote = job.get("remote", False) or "remote" in (location or "").lower()

        slug = job.get("slug", "")
        url = job.get("url", "")
        if not url and slug:
            url = f"https://cryptojobslist.com/jobs/{slug}"

        results.append({
            "title": title,
            "company": job.get("company", {}).get("name", "") if isinstance(job.get("company"), dict) else job.get("company", ""),
            "location": location or ("Remote" if is_remote else "Not specified"),
            "url": url,
            "source": "cryptojobslist",
            "description": _strip_html(job.get("description", ""))[:3000],
            "salary_min": sal_min,
            "salary_max": sal_max,
            "date_posted": job.get("date", "") or job.get("created_at", ""),
            "is_remote": is_remote,
            "company_size": "",
        })
        if len(results) >= max_results:
            break

    logger.info("CryptoJobsList (JSON): found %d matching jobs", len(results))
    return results


def _parse_cryptojobs_rss(
    roles: list[str] | None,
    max_results: int,
) -> list[dict]:
    """Fallback RSS parser for CryptoJobsList."""
    try:
        resp = requests.get(
            "https://cryptojobslist.com/rss",
            headers={"User-Agent": _HEADERS["User-Agent"], "Accept": "application/rss+xml,application/xml,text/xml"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("CryptoJobsList RSS failed: %s", e)
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        logger.warning("CryptoJobsList RSS parse failed: %s", e)
        return []

    ns = {
        "dc": "http://purl.org/dc/elements/1.1/",
        "media": "http://search.yahoo.com/mrss/",
    }

    results: list[dict] = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        if not title:
            continue

        company = item.findtext("dc:creator", "", ns) or ""

        if roles and not _match_roles_crypto(title, roles):
            continue

        desc_html = item.findtext("description", "")
        description = _strip_html(desc_html)

        location = item.findtext("media:location", "", ns) or item.findtext("location", "")
        is_remote = "remote" in (location or "").lower()
        if not location:
            location = "Remote" if is_remote else "Not specified"

        results.append({
            "title": title,
            "company": company,
            "location": location,
            "url": item.findtext("link", ""),
            "source": "cryptojobslist",
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "date_posted": item.findtext("pubDate", ""),
            "is_remote": is_remote,
            "company_size": "",
        })
        if len(results) >= max_results:
            break

    logger.info("CryptoJobsList (RSS): found %d matching jobs", len(results))
    return results
