"""Web3.career — Web3/crypto jobs via its official API or public listings.

The official API is preferred, but it requires a per-user token. Fresh
Questboard installs therefore use Web3.career's public, server-rendered job
pages. Those pages carry job cards plus JobPosting JSON-LD with dates,
descriptions, locations, and salary metadata. When
``WEB3_CAREER_API_TOKEN`` is configured, this scraper switches to ``/api/v1``
and obeys the API's mandatory ``apply_url`` attribution requirement.

Both surfaces are windowed newest-first feeds, not full snapshots. Absence
from one pull cannot prove an older posting expired; ordinary URL verification
and the registry's stale window handle lifecycle instead.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _match_roles_crypto,
    _strip_html,
    date_confidence_for,
    extract_salary_range,
    rank_by_relevance,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://web3.career"
_API_URL = f"{_BASE_URL}/api/v1"
_API_TOKEN_ENV = "WEB3_CAREER_API_TOKEN"
_PUBLIC_PAGES_PER_LANE = 2
_PUBLIC_WORKERS = 6
_PUBLIC_HEADERS = {
    **_HEADERS,
    # The shared scraper headers request JSON. Web3.career content-negotiates
    # listing routes and returns 406/500 for that Accept value, so public
    # pages must explicitly identify themselves as HTML navigation.
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# The API accepts only exact tags from its published enum. Public routes also
# include leadership/founding pages not exposed as API tags, so selection is
# kept separate and an invalid tag can never silently produce a false zero.
_API_TAGS: frozenset[str] = frozenset({
    "ai", "analyst", "backend", "bitcoin", "blockchain", "community-manager",
    "crypto", "cryptography", "cto", "customer-support", "dao", "data-science",
    "defi", "design", "developer-relations", "devops", "entry-level", "front-end",
    "full-stack", "gaming", "golang", "intern", "java", "javascript", "layer-2",
    "marketing", "mobile", "non-tech", "open-source", "product-manager",
    "project-manager", "react", "research", "ruby", "rust", "sales", "solana",
    "solidity", "smart-contract", "web3-py", "web3js", "zero-knowledge",
})

_ECOSYSTEM_TAGS: frozenset[str] = frozenset({
    "arbitrum", "avalanche", "bitcoin", "cosmos", "ethereum", "layer-2",
    "near", "optimism", "polygon", "solana", "sui", "ton", "zero-knowledge",
})

_JOB_PATH_RE = re.compile(r"^/[^/?#]+/\d+$")


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def _job_key(title: object, company: object) -> str:
    return re.sub(r"[^a-z0-9]", "", f"{_clean_text(title)} {_clean_text(company)}".lower())


def _salary_from_jsonld(payload: dict) -> tuple[float | None, float | None, str, str]:
    base = payload.get("baseSalary")
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return None, None, "", ""

    def number(raw: object) -> float | None:
        try:
            return float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            return None

    period = {
        "YEAR": "annual",
        "MONTH": "monthly",
        "WEEK": "weekly",
        "DAY": "daily",
        "HOUR": "hourly",
    }.get(str(value.get("unitText") or "").strip().upper(), "")
    return (
        number(value.get("minValue")),
        number(value.get("maxValue")),
        str(base.get("currency") or "").strip().upper(),
        period,
    )


def _parse_public_page(html: str) -> list[dict]:
    """Parse cards by identity, using JSON-LD only as optional enrichment.

    Web3.career occasionally omits JSON-LD for a card on paginated pages.
    Zipping the two arrays shifts every later description onto the wrong job,
    so enrichment is matched by normalized title and company instead.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    structured: dict[str, list[dict]] = defaultdict(list)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text() or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("@type") != "JobPosting":
            continue
        org = payload.get("hiringOrganization")
        company = org.get("name") if isinstance(org, dict) else ""
        structured[_job_key(payload.get("title"), company)].append(payload)

    jobs: list[dict] = []
    for row in soup.select("tr[data-jobid]"):
        title_node = row.select_one("h2")
        company_node = row.select_one("h3")
        link = row.select_one("a[href][data-jobid]")
        title = _clean_text(title_node.get_text(" ", strip=True) if title_node else "")
        company = _clean_text(company_node.get_text(" ", strip=True) if company_node else "")
        href = str(link.get("href") or "").strip() if link else ""
        if not title or not company or not _JOB_PATH_RE.fullmatch(href):
            continue

        key = _job_key(title, company)
        details = structured[key].pop(0) if structured[key] else {}
        location_node = row.select_one(".job-location-mobile")
        location = _clean_text(location_node.get_text(" ", strip=True) if location_node else "")
        location = re.sub(r"^📍\s*", "", location)
        location = re.sub(r"\s+,\s*", ", ", location)
        tags = [
            _clean_text(node.get_text(" ", strip=True)).lower()
            for node in row.select(".cell-tags a")
            if _clean_text(node.get_text(" ", strip=True))
        ]
        # Some rows report a broad country in the location cell while the
        # employer-supplied title itself says "Remote" (for example, LS
        # Solutions' Remote Founding Engineer). Preserve that explicit signal.
        is_remote = (
            location.casefold() in {"remote", "anywhere"}
            or "remote" in tags
            or bool(re.search(r"\bremote\b", title, re.IGNORECASE))
        )

        date_node = row.select_one("time[datetime]")
        posted_at = str(date_node.get("datetime") or "").strip() if date_node else ""
        posted_at = posted_at or str(details.get("datePosted") or "").strip()

        salary_node = row.select_one(".cell-salary")
        salary_text = _clean_text(salary_node.get_text(" ", strip=True) if salary_node else "")
        extracted = extract_salary_range(salary_text)
        salary_min = extracted.salary_min
        salary_max = extracted.salary_max
        salary_currency = extracted.currency or ""
        salary_period = extracted.period or ""
        ld_min, ld_max, ld_currency, ld_period = _salary_from_jsonld(details)
        if salary_min is None and salary_max is None:
            salary_min, salary_max = ld_min, ld_max
        # Card copy often abbreviates compensation as "$180k-$220k" while
        # the matched JobPosting record supplies the unambiguous ISO currency
        # and cadence. Enrich only missing metadata; keep the card's values.
        salary_currency = salary_currency or ld_currency
        salary_period = salary_period or ld_period

        description = _strip_html(str(details.get("description") or ""))[:6000]
        ecosystems = sorted({tag for tag in tags if tag in _ECOSYSTEM_TAGS})
        jobs.append({
            "title": title,
            "company": company,
            "location": location or "Not specified",
            "url": urljoin(_BASE_URL, href),
            "source": "web3career",
            "description": description,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_currency": salary_currency,
            "salary_period": salary_period,
            # The public board explicitly labels these as estimates on many
            # cards. Never promote them to employer-reported compensation.
            "salary_source": (
                "source_estimate"
                if salary_min is not None or salary_max is not None
                else None
            ),
            "date_posted": posted_at,
            "date_confidence": date_confidence_for(posted_at),
            "is_remote": is_remote,
            "remote_flag_reported": bool(is_remote),
            "company_size": "",
            "crypto": True,
            "industry_tags": ["crypto"],
            "ecosystem_tags": ecosystems,
            "web3career_tags": tags,
        })
    return jobs


def _extract_api_jobs(payload: object) -> list[dict]:
    """Defensively locate jobs in the API's documented mixed root array."""
    if isinstance(payload, dict):
        for key in ("jobs", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
        return []
    if not isinstance(payload, list):
        return []
    for item in payload:
        if isinstance(item, list):
            return [row for row in item if isinstance(row, dict)]
    return [row for row in payload if isinstance(row, dict)]


def _normalize_api_job(job: dict) -> dict:
    tags = [str(tag).strip().lower() for tag in (job.get("tags") or []) if str(tag).strip()]
    salary = extract_salary_range(str(job.get("salary") or ""))
    apply_url = str(job.get("apply_url") or "").strip()
    listing_url = str(job.get("url") or "").strip()
    location = _clean_text(job.get("location")) or "Not specified"
    is_remote = bool(job.get("remote")) or location.casefold() in {"remote", "anywhere"}
    posted_at = job.get("postedAt") or job.get("posted_at") or job.get("datePosted") or ""
    return {
        "title": _clean_text(job.get("title")),
        "company": _clean_text(job.get("company")),
        # API terms require apply_url for user-facing links.
        "url": apply_url or listing_url,
        "source_listing_url": listing_url,
        "source": "web3career",
        "location": location,
        "description": _strip_html(str(job.get("description") or ""))[:6000],
        "salary_min": salary.salary_min,
        "salary_max": salary.salary_max,
        "salary_currency": salary.currency or "",
        "salary_period": salary.period or "",
        "salary_source": (
            "source_estimate"
            if salary.salary_min is not None or salary.salary_max is not None
            else None
        ),
        "date_posted": posted_at,
        "date_confidence": date_confidence_for(posted_at),
        "is_remote": is_remote,
        "remote_flag_reported": bool(job.get("remote")),
        "company_size": "",
        "crypto": True,
        "industry_tags": ["crypto"],
        "ecosystem_tags": sorted({tag for tag in tags if tag in _ECOSYSTEM_TAGS}),
        "web3career_tags": tags,
    }


def _role_tags(roles: list[str] | None) -> list[str]:
    text = " ".join(roles or []).lower()
    tags: list[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    if any(term in text for term in ("data", "analytics", "scientist")):
        add("data-science")
        add("analyst")
    if any(term in text for term in ("engineer", "engineering", "developer", "platform", "infrastructure")):
        add("engineer")  # public route; not an API tag
    if any(term in text for term in ("manager", "director", "head", "vp", "chief")) and any(
        term in text for term in ("engineer", "engineering", "platform", "infrastructure", "data")
    ):
        add("engineering-manager")  # public-only route
    mappings = {
        "product": "product-manager",
        "project": "project-manager",
        "program": "project-manager",
        "marketing": "marketing",
        "sales": "sales",
        "design": "design",
        "research": "research",
        "devops": "devops",
        "backend": "backend",
        "front end": "front-end",
        "frontend": "front-end",
        "full stack": "full-stack",
        "solana": "solana",
        "solidity": "solidity",
        "smart contract": "smart-contract",
        "security": "cryptography",
        "community": "community-manager",
        "customer support": "customer-support",
        "founding": "founding-engineer",  # public-only route
    }
    for signal, tag in mappings.items():
        if signal in text:
            add(tag)
    return tags[:5]


def _public_urls(roles: list[str] | None, locations: list[str] | None) -> list[str]:
    routes = [f"/{tag}-jobs" for tag in _role_tags(roles)]
    if any(str(location).strip().casefold() in {"remote", "anywhere"} for location in (locations or [])):
        routes.append("/remote-jobs")
    # Global newest-job safety net for roles that do not map to a tag.
    routes.append("/")
    routes = list(dict.fromkeys(routes))
    urls: list[str] = []
    for route in routes:
        pages = 1 if route == "/" else _PUBLIC_PAGES_PER_LANE
        for page in range(1, pages + 1):
            suffix = f"?page={page}" if page > 1 else ""
            urls.append(f"{_BASE_URL}{route}{suffix}")
    return urls


def _fetch_public_html(url: str) -> str:
    response = requests.get(url, headers=_PUBLIC_HEADERS, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.text


def _search_public(
    roles: list[str] | None,
    locations: list[str] | None,
    *,
    match_mode: str,
    include_founding: bool,
    max_results: int,
) -> list[dict]:
    urls = _public_urls(roles, locations)
    pages: dict[str, str] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=min(_PUBLIC_WORKERS, len(urls))) as pool:
        futures = {pool.submit(_fetch_public_html, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                pages[url] = future.result()
            except Exception as exc:
                failures.append(f"{type(exc).__name__}: {exc}")
                logger.warning("Web3.career public page failed (%s): %s", url, exc)
    if not pages:
        raise RuntimeError(
            "all Web3.career public listing pages failed"
            + (f": {failures[0][:240]}" if failures else "")
        )

    seen: set[str] = set()
    results: list[dict] = []
    parsed_rows = 0
    # Restore deterministic lane/page order after concurrent fetching.
    for url in urls:
        jobs = _parse_public_page(pages.get(url, ""))
        parsed_rows += len(jobs)
        for job in jobs:
            target = str(job.get("url") or "")
            if not target or target in seen:
                continue
            seen.add(target)
            if roles and not _match_roles_crypto(
                str(job.get("title") or ""),
                roles,
                match_mode=match_mode,
                include_founding=include_founding,
            ):
                continue
            results.append(job)
    if not parsed_rows:
        raise RuntimeError("Web3.career public page schema returned no job rows")
    return rank_by_relevance(results, roles)[:max_results]


def _fetch_api_payload(token: str, *, tag: str | None, remote_only: bool, limit: int) -> object:
    params: dict[str, object] = {
        "token": token,
        "limit": max(1, min(limit, 100)),
        "show_description": "true",
    }
    if tag:
        params["tag"] = tag
    if remote_only:
        params["remote"] = "true"
    for attempt in range(3):
        response = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
            return response.json()
        if attempt < 2:
            retry_after = response.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else 0.5 * (2 ** attempt)
            time.sleep(min(delay, 4.0))
    response.raise_for_status()
    return []


def _search_api(
    token: str,
    roles: list[str] | None,
    locations: list[str] | None,
    *,
    match_mode: str,
    include_founding: bool,
    max_results: int,
) -> list[dict]:
    tags = [tag for tag in _role_tags(roles) if tag in _API_TAGS]
    queries: list[str | None] = [None, *tags]
    remote_only = bool(locations) and all(
        str(location).strip().casefold() in {"remote", "anywhere"}
        for location in (locations or [])
    )
    raw: list[dict] = []
    # There is no cursor. Exact-tag queries recover relevant jobs that have
    # fallen outside the global newest 100.
    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        futures = {
            pool.submit(
                _fetch_api_payload,
                token,
                tag=tag,
                remote_only=remote_only,
                limit=min(max_results, 100),
            ): tag
            for tag in queries
        }
        for future in as_completed(futures):
            raw.extend(_extract_api_jobs(future.result()))

    results: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        job = _normalize_api_job(item)
        url = str(job.get("url") or "")
        if not job.get("title") or not job.get("company") or not url or url in seen:
            continue
        seen.add(url)
        if roles and not _match_roles_crypto(
            str(job.get("title") or ""),
            roles,
            match_mode=match_mode,
            include_founding=include_founding,
        ):
            continue
        results.append(job)
    return rank_by_relevance(results, roles)[:max_results]


@register_scraper(
    name="web3career",
    display_name="Web3.career",
    url=_BASE_URL,
    description="Web3, crypto and blockchain jobs via Web3.career",
    category="crypto",
    enabled_by_default=False,
    stale_after_days=45,
)
def search_web3career(
    roles: list[str] | None = None,
    max_results: int = 50,
    locations: list[str] | None = None,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    api_token: str | None = None,
    **kwargs: Any,
) -> list[dict]:
    """Return matching Web3.career jobs, preferring its tokenized API."""
    token = (api_token or os.environ.get(_API_TOKEN_ENV) or "").strip()
    if token:
        try:
            jobs = _search_api(
                token,
                roles,
                locations,
                match_mode=match_mode,
                include_founding=include_founding,
                max_results=max_results,
            )
            if jobs:
                logger.info("Web3.career API: found %d matching jobs", len(jobs))
                return jobs
            logger.warning("Web3.career API returned no matching rows; checking public listings")
        except Exception as exc:
            # Never log the token or a prepared URL; credentials are in the
            # API query string.
            logger.warning("Web3.career API failed; using public listings: %s", exc)

    jobs = _search_public(
        roles,
        locations,
        match_mode=match_mode,
        include_founding=include_founding,
        max_results=max_results,
    )
    logger.info("Web3.career public listings: found %d matching jobs", len(jobs))
    return jobs
