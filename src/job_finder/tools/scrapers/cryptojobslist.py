"""CryptoJobsList — Crypto/Web3/Blockchain jobs via embedded Next.js data.

CryptoJobsList's previous public surfaces (``/api/jobs`` JSON and ``/rss``)
both returned 403 starting spring 2026. Their site is a Next.js app that
server-renders the job list into a ``<script id="__NEXT_DATA__">`` blob,
which is publicly reachable on plain GETs. We parse that blob and walk to
``props.pageProps.jobs``.

Pagination via ``?page=N`` (25 jobs per page). Category filtering via
``?category=engineering`` to bias toward technical roles. Per-job rich
salary lives in an embedded JSON-LD string at ``jobPostingJSONLD``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _match_roles_crypto,
)

logger = logging.getLogger(__name__)


_BASE_URL = "https://cryptojobslist.com"
_DEFAULT_CATEGORY = "engineering"
_PAGE_SIZE = 25
_MAX_PAGES = 4  # 4 pages × 25 = 100 jobs max, plenty
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"[^>]*>(.+?)</script>',
    re.DOTALL,
)


def _fetch_html(url: str) -> str:
    """Fetch a page, returning HTML or empty string on any failure."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("CryptoJobsList %s returned %s", url, resp.status_code)
            return ""
        return resp.text
    except requests.RequestException as exc:
        logger.warning("CryptoJobsList fetch failed (%s): %s", url, exc)
        return ""


def _extract_next_data_jobs(html: str) -> list[dict]:
    """Pull the ``jobs`` array out of a Next.js ``__NEXT_DATA__`` script.

    Returns [] when the blob is missing, malformed, or doesn't contain
    a recognizable jobs list — the scraper degrades silently rather than
    surfacing parsing errors to the user.
    """
    if not html:
        return []
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("CryptoJobsList __NEXT_DATA__ unparseable: %s", exc)
        return []

    # Walk the standard Next.js page-props path first; fall back to a
    # depth-bounded search so the parser survives minor schema shifts.
    page_props = (
        data.get("props", {}).get("pageProps", {})
        if isinstance(data, dict) else {}
    )
    jobs = page_props.get("jobs")
    if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) and "jobTitle" in jobs[0]:
        return jobs

    return _find_jobs_recursively(data, max_depth=8) or []


def _find_jobs_recursively(obj: Any, *, max_depth: int = 8, depth: int = 0) -> list[dict] | None:
    """Defensive walk: find a list of job-shaped dicts anywhere in the tree."""
    if depth > max_depth:
        return None
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("jobs", "allJobs") and isinstance(value, list) and value:
                first = value[0] if isinstance(value[0], dict) else None
                if first and ("jobTitle" in first or "title" in first):
                    return value
            found = _find_jobs_recursively(value, max_depth=max_depth, depth=depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_jobs_recursively(item, max_depth=max_depth, depth=depth + 1)
            if found:
                return found
    return None


def _extract_salary_from_jsonld(jsonld_str: str | None) -> tuple[int | None, int | None]:
    """Pull (min, max) salary in USD from the embedded JobPosting JSON-LD."""
    if not jsonld_str:
        return None, None
    try:
        ld = json.loads(jsonld_str)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None, None
    graph = ld.get("@graph") if isinstance(ld, dict) else None
    posting = graph[0] if isinstance(graph, list) and graph else (ld if isinstance(ld, dict) else None)
    if not isinstance(posting, dict):
        return None, None
    base = posting.get("baseSalary") or {}
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return None, None
    min_v = value.get("minValue")
    max_v = value.get("maxValue")
    try:
        return (int(min_v) if min_v else None, int(max_v) if max_v else None)
    except (TypeError, ValueError):
        return None, None


def _normalize_next_job(job: dict) -> dict:
    """Map one CryptoJobsList Next.js job object to our standard dict."""
    title = job.get("jobTitle") or job.get("title") or ""
    company = job.get("companyName") or job.get("company") or ""
    location_raw = (job.get("jobLocation") or "").strip()
    is_remote = bool(job.get("remote")) or "remote" in (location_raw.lower())
    if not location_raw:
        location_raw = "Remote" if is_remote else "Not specified"

    slug = job.get("seoSlug") or ""
    url = f"{_BASE_URL}/jobs/{slug}" if slug else ""

    sal_min, sal_max = _extract_salary_from_jsonld(job.get("jobPostingJSONLD"))

    # tags often include the category + employment type; expose as a comma
    # joined string in description for downstream keyword scoring.
    tags = job.get("tags") or []
    tags_str = ", ".join(t for t in tags if isinstance(t, str)) if tags else ""

    return {
        "title": title,
        "company": company,
        "location": location_raw,
        "url": url,
        "source": "cryptojobslist",
        "description": tags_str,  # Tags are the only public description in __NEXT_DATA__
        "salary_min": sal_min,
        "salary_max": sal_max,
        "date_posted": job.get("publishedAt") or "",
        "is_remote": is_remote,
        "company_size": "",
    }


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
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch crypto/web3 jobs from CryptoJobsList by parsing __NEXT_DATA__.

    Iterates pages until ``max_results`` is satisfied or ``_MAX_PAGES`` is hit.
    Role matching uses :func:`_match_roles_crypto` so titles containing
    web3/blockchain/defi/zk/etc. terms pass even when they don't
    word-match the user's normal target roles.
    """
    logger.info("Fetching jobs from CryptoJobsList...")
    results: list[dict] = []
    seen_urls: set[str] = set()

    for page in range(1, _MAX_PAGES + 1):
        if len(results) >= max_results:
            break

        query = f"?category={_DEFAULT_CATEGORY}"
        if page > 1:
            query += f"&page={page}"
        url = f"{_BASE_URL}/{query}"
        html = _fetch_html(url)
        if not html:
            break

        raw_jobs = _extract_next_data_jobs(html)
        if not raw_jobs:
            break

        new_this_page = 0
        for raw in raw_jobs:
            if len(results) >= max_results:
                break
            normalized = _normalize_next_job(raw)
            if not normalized["title"]:
                continue
            if normalized["url"] in seen_urls:
                continue
            if roles and not _match_roles_crypto(
                normalized["title"],
                roles,
                match_mode=match_mode,
                include_founding=include_founding,
            ):
                continue
            results.append(normalized)
            seen_urls.add(normalized["url"])
            new_this_page += 1

        # No new urls means we've hit the end of CryptoJobsList's listing
        # (the same jobs cycle back when you paginate past the actual end).
        if new_this_page == 0:
            break

    logger.info("CryptoJobsList: found %d matching jobs", len(results))
    return results
