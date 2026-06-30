"""Getro — Crypto/VC talent-network jobs via the free board-search API.

Getro powers the "jobs" boards for many crypto funds and VC talent networks
(Coinbase Ventures, the Blockchain Association, a16z portfolios, etc.). Each
network has a numeric ``collection`` id whose jobs are searchable through a
free, unauthenticated endpoint::

    POST https://api.getro.com/api/v2/collections/<network_id>/search/jobs
    body: {"hitsPerPage": 100, "page": 0, "query": ""}

The response is ``{"results": {"jobs": [...], "count": <total>}}``. The API
caps each page at ~20 jobs regardless of ``hitsPerPage``, so we paginate via
``page`` until ``max_results`` is satisfied. Each job carries ``title``,
``organization`` (name / head_count / stage), ``url`` (the real listing, often
on LinkedIn / Ashby / a career page), ``work_mode`` (remote|on_site|hybrid),
``locations``, ``seniority``, ``skills``, and ``compensation_*_cents``. The
search response has no description body (``has_description`` only flags whether
one exists), so we synthesize a short description from seniority + skills.
"""

from __future__ import annotations

import logging

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _match_roles_crypto,
    _strip_html,
)

logger = logging.getLogger(__name__)


_API_BASE = "https://api.getro.com/api/v2/collections"
_PAGE_SIZE = 20  # API caps each page near 20 regardless of hitsPerPage
_MAX_PAGES = 5  # 5 pages × 20 = 100 jobs per network ceiling

# Seed crypto / VC talent-network collections confirmed to return HTTP 200.
# (slug, network_id) — slug is informational, network_id drives the endpoint.
_GETRO_NETWORKS: list[tuple[str, int]] = [
    ("coinbase", 1625),
    ("blockchain-association", 869),
]

# Getro's search endpoint POSTs JSON, so it needs a Content-Type the shared
# GET-oriented _HEADERS dict doesn't carry. Build a POST-flavored copy once.
_POST_HEADERS = {**_HEADERS, "Content-Type": "application/json"}


def _fetch_search(network_id: int, page: int) -> list[dict]:
    """POST one page of a Getro collection search; [] on any failure.

    Returns the raw ``results.jobs`` list for the page. Wrapped so the caller
    can ``continue`` past a flaky network, and so tests can patch one helper.
    """
    url = f"{_API_BASE}/{network_id}/search/jobs"
    body = {"hitsPerPage": 100, "page": page, "query": ""}
    try:
        resp = requests.post(url, headers=_POST_HEADERS, json=body, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Getro %s page %d returned %s", network_id, page, resp.status_code)
            return []
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Getro fetch failed (network %s, page %d): %s", network_id, page, exc)
        return []
    except ValueError as exc:
        logger.warning("Getro returned invalid JSON (network %s, page %d): %s", network_id, page, exc)
        return []

    results = data.get("results") if isinstance(data, dict) else None
    jobs = results.get("jobs") if isinstance(results, dict) else None
    return jobs if isinstance(jobs, list) else []


def _cents_to_dollars(value: object) -> float | None:
    """Convert a ``*_cents`` integer to whole dollars, or None."""
    if value is None:
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        return None


def _normalize_job(job: dict) -> dict:
    """Map one Getro search job object to our standard scraper dict."""
    title = job.get("title") or ""

    org = job.get("organization") or {}
    company = org.get("name") if isinstance(org, dict) else ""
    head_count = org.get("head_count") if isinstance(org, dict) else None
    company_size = str(head_count) if isinstance(head_count, int) and head_count > 0 else ""

    work_mode = (job.get("work_mode") or "").lower()
    is_remote = work_mode == "remote"

    locations = job.get("locations") or []
    if isinstance(locations, list) and locations:
        location = ", ".join(str(loc) for loc in locations if loc)
    else:
        location = "Remote" if is_remote else "Not specified"

    # The search response carries no description body, only structured signals.
    # Surface seniority + skills as the description so downstream keyword scoring
    # has something domain-relevant to work with.
    parts: list[str] = []
    seniority = job.get("seniority")
    if isinstance(seniority, str) and seniority:
        parts.append(f"Seniority: {seniority}")
    skills = job.get("skills") or []
    if isinstance(skills, list) and skills:
        skill_str = ", ".join(s for s in skills if isinstance(s, str))
        if skill_str:
            parts.append(f"Skills: {skill_str}")
    description = _strip_html("\n".join(parts))[:3000]

    sal_min = _cents_to_dollars(job.get("compensation_amount_min_cents"))
    sal_max = _cents_to_dollars(job.get("compensation_amount_max_cents"))

    return {
        "title": title,
        "company": company or "",
        "location": location,
        "url": job.get("url") or "",
        "source": "getro",
        "description": description,
        "salary_min": sal_min,
        "salary_max": sal_max,
        "date_posted": job.get("created_at") or "",
        "is_remote": is_remote,
        "company_size": company_size,
    }


@register_scraper(
    name="getro",
    display_name="Getro (Crypto + VC networks)",
    url="https://getro.com",
    description="Crypto and venture-backed startup jobs via Getro talent-network boards",
    category="crypto",
    # Opt-in like cryptojobslist — crypto-domain listings are noise for a
    # non-crypto job search, so profiles enable it explicitly in config.
    enabled_by_default=False,
)
def search_getro(
    roles: list[str] | None = None,
    max_results: int = 50,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch crypto/VC-network jobs from Getro's free board-search API.

    Iterates each seed network's pages until ``max_results`` is satisfied or
    ``_MAX_PAGES`` is hit. Role matching uses :func:`_match_roles_crypto` so
    crypto/web3 titles ("Solidity Engineer", "ZK Researcher") pass even when
    they don't word-match the user's normal target roles — these boards are
    crypto-domain by construction.
    """
    logger.info("Fetching jobs from Getro talent-network boards...")
    results: list[dict] = []
    seen_urls: set[str] = set()

    for slug, network_id in _GETRO_NETWORKS:
        if len(results) >= max_results:
            break
        for page in range(_MAX_PAGES):
            if len(results) >= max_results:
                break
            raw_jobs = _fetch_search(network_id, page)
            if not raw_jobs:
                break  # end of this network's listings (or a transient failure)

            new_this_page = 0
            for raw in raw_jobs:
                if len(results) >= max_results:
                    break
                if not isinstance(raw, dict):
                    continue
                normalized = _normalize_job(raw)
                if not normalized["title"]:
                    continue
                url = normalized["url"]
                if url and url in seen_urls:
                    continue
                if roles and not _match_roles_crypto(
                    normalized["title"],
                    roles,
                    match_mode=match_mode,
                    include_founding=include_founding,
                ):
                    continue
                results.append(normalized)
                if url:
                    seen_urls.add(url)
                new_this_page += 1

            # A short page means we've reached the end of this network's jobs.
            if len(raw_jobs) < _PAGE_SIZE:
                break
            # Page yielded only already-seen/filtered jobs and we're not making
            # progress toward max_results — stop paginating this network.
            if new_this_page == 0:
                break

    logger.info("Getro: found %d matching jobs", len(results))
    return results
