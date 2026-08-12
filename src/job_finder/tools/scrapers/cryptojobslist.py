"""CryptoJobsList — Crypto/Web3/Blockchain jobs via embedded Next.js data.

CryptoJobsList's previous public surfaces (``/api/jobs`` JSON and ``/rss``)
both returned 403 starting spring 2026. Their site is a Next.js app that
server-renders the job list into a ``<script id="__NEXT_DATA__">`` blob,
which is publicly reachable on plain GETs. We parse that blob and walk to
``props.pageProps.jobs``.

Pagination uses ``?page=N`` (25 jobs per page). CryptoJobsList's category
navigation is path-based (``/data`` and ``/engineering``); the old
``?category=engineering`` query is ignored by the current site and returns the
general feed. Retained matches are enriched from their public detail page,
whose ``pageProps.job`` carries the full description and current salary.
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _match_roles_crypto,
    _strip_html,
    date_confidence_for,
)

logger = logging.getLogger(__name__)


_BASE_URL = "https://cryptojobslist.com"
_PAGE_SIZE = 25
# The source mixes featured and organic rows, so a relevant role can sit well
# behind the first 100 results. Six pages per lane scans at most 450 list rows
# across the two focused lanes plus the general fallback, while detail requests
# are made only for retained matches.
_MAX_PAGES_PER_LANE = 6
_LISTING_ROUTES = ("data", "engineering", "")
_DETAIL_WORKERS = 6
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


def _extract_next_data_detail_job(html: str) -> dict:
    """Return the detail page's ``pageProps.job`` object, if present."""
    if not html:
        return {}
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    job = data.get("props", {}).get("pageProps", {}).get("job")
    return job if isinstance(job, dict) else {}


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


def _number_or_none(value: object) -> int | float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def _extract_salary(job: dict) -> tuple[int | float | None, int | float | None, str, str]:
    """Read the current ``salary`` object, with legacy JSON-LD fallback."""
    salary = job.get("salary")
    if isinstance(salary, dict):
        minimum = _number_or_none(salary.get("minValue"))
        maximum = _number_or_none(salary.get("maxValue"))
        if minimum is not None or maximum is not None:
            unit = str(salary.get("unitText") or "").strip().lower()
            periods = {
                "year": "annual",
                "annual": "annual",
                "hour": "hourly",
                "day": "daily",
                "week": "weekly",
                "month": "monthly",
            }
            return (
                minimum,
                maximum,
                str(salary.get("currency") or "").strip().upper(),
                periods.get(unit, ""),
            )
    minimum, maximum = _extract_salary_from_jsonld(job.get("jobPostingJSONLD"))
    return minimum, maximum, "", ""


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

    sal_min, sal_max, salary_currency, salary_period = _extract_salary(job)

    # tags often include the category + employment type; expose as a comma
    # joined string in description for downstream keyword scoring.
    tags = job.get("tags") or []
    tags_str = ", ".join(t for t in tags if isinstance(t, str)) if tags else ""
    description = _strip_html(str(job.get("jobDescription") or "")) or tags_str
    posted_at = job.get("publishedAt") or ""

    return {
        "title": title,
        "company": company,
        "location": location_raw,
        "url": url,
        "source": "cryptojobslist",
        "description": description,
        "salary_min": sal_min,
        "salary_max": sal_max,
        "salary_currency": salary_currency,
        "salary_period": salary_period,
        "salary_source": (
            "reported" if sal_min is not None or sal_max is not None else None
        ),
        "date_posted": posted_at,
        "date_confidence": date_confidence_for(posted_at),
        "is_remote": is_remote,
        "remote_flag_reported": True,
        "company_size": "",
    }


def _fetch_detail_job(url: str) -> dict:
    """Fetch one public job detail object; failures leave list data intact."""
    return _extract_next_data_detail_job(_fetch_html(url))


def _enrich_job(job: dict) -> dict:
    """Replace thin list-card data with the richer public detail payload."""
    detail = _fetch_detail_job(str(job.get("url") or ""))
    if not detail:
        return job
    rich = _normalize_next_job(detail)
    for key in (
        "description",
        "salary_min",
        "salary_max",
        "salary_currency",
        "salary_period",
        "salary_source",
        "date_posted",
        "date_confidence",
        "location",
        "is_remote",
        "remote_flag_reported",
    ):
        value = rich.get(key)
        if value not in (None, ""):
            job[key] = value
    return job


def _enrich_jobs(jobs: list[dict]) -> list[dict]:
    """Enrich retained matches concurrently without changing result order."""
    if not jobs:
        return jobs
    enriched: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=min(_DETAIL_WORKERS, len(jobs))) as pool:
        futures = {pool.submit(_enrich_job, dict(job)): index for index, job in enumerate(jobs)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                enriched[index] = future.result()
            except Exception as exc:
                logger.debug("CryptoJobsList detail enrichment failed: %s", exc)
                enriched[index] = jobs[index]
    return [enriched[index] for index in range(len(jobs))]


def _listing_url(route: str, page: int) -> str:
    base = f"{_BASE_URL}/{route}" if route else f"{_BASE_URL}/"
    return f"{base}?page={page}" if page > 1 else base


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
    enrich_details: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch crypto/web3 jobs from CryptoJobsList by parsing __NEXT_DATA__.

    Scans the data and engineering lanes plus the general fallback, until
    ``max_results`` is satisfied or a lane repeats its raw URLs.
    Role matching uses :func:`_match_roles_crypto` so titles containing
    web3/blockchain/defi/zk/etc. terms pass even when they don't
    word-match the user's normal target roles.
    """
    logger.info("Fetching jobs from CryptoJobsList...")
    results: list[dict] = []
    seen_urls: set[str] = set()

    for route in _LISTING_ROUTES:
        lane_seen_urls: set[str] = set()
        for page in range(1, _MAX_PAGES_PER_LANE + 1):
            if len(results) >= max_results:
                break
            html = _fetch_html(_listing_url(route, page))
            if not html:
                break
            raw_jobs = _extract_next_data_jobs(html)
            if not raw_jobs:
                break

            raw_new_this_page = 0
            for raw in raw_jobs:
                normalized = _normalize_next_job(raw)
                url = normalized["url"]
                if not normalized["title"] or not url:
                    continue
                if url in lane_seen_urls:
                    continue
                lane_seen_urls.add(url)
                raw_new_this_page += 1
                if url in seen_urls:
                    continue
                # Mark every raw URL as seen before role filtering. A page with
                # zero matches is not the end of the feed; it must not make a
                # later page unreachable.
                seen_urls.add(url)
                if roles and not _match_roles_crypto(
                    normalized["title"],
                    roles,
                    match_mode=match_mode,
                    include_founding=include_founding,
                ):
                    continue
                results.append(normalized)
                if len(results) >= max_results:
                    break

            # CryptoJobsList cycles earlier rows after the end of a lane. Stop
            # only when the raw page is empty/repeated, never merely because
            # none of its titles matched this person's roles.
            if raw_new_this_page == 0:
                break
        if len(results) >= max_results:
            break

    if enrich_details:
        results = _enrich_jobs(results)
    logger.info("CryptoJobsList: found %d matching jobs", len(results))
    return results
