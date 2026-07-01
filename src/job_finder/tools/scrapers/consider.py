"""Consider: VC talent-network jobs embedded in board HTML.

Consider (consider.com) powers the "jobs" boards for many VC / crypto funds,
including a16z crypto's portfolio board at https://a16zcrypto.com/jobs/. Unlike
Getro's JSON API, a Consider board server-renders every listing straight into
the page inside a ``const portfolioJobs = [...]`` array, grouped by company::

    const portfolioJobs = [{"company": "...", "jobs": [ {...}, ... ]}, ...]

Each job carries ``title``, ``companyName``, ``url`` (the real listing on
Ashby / Lever / Greenhouse / a career page), ``locations``, ``remote``,
``salary`` ({currency, minValue, maxValue, period}), ``seniorities``,
``skills``, ``functions``, and ``createdAt``. We fetch the board HTML, pull the
array out with a balanced-bracket scan (the payload is valid JSON), flatten the
company groups, and normalize to the standard scraper dict. No auth, no key.

The search response carries no description body, so we synthesize a short one
from seniority + function + skills for downstream keyword scoring.
"""

from __future__ import annotations

import json
import logging

import requests

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import (
    _HEADERS,
    _TIMEOUT,
    _match_roles,
    _match_roles_crypto,
    _strip_html,
)

logger = logging.getLogger(__name__)


# Consider boards to scrape. (slug, board_url, is_crypto). slug is
# informational, board_url drives the fetch, is_crypto flags the board as a
# crypto/web3 talent network so its jobs get crypto-aware role matching.
_CONSIDER_BOARDS: list[tuple[str, str, bool]] = [
    ("a16z-crypto", "https://a16zcrypto.com/jobs/", True),
]

# The board page is HTML, not JSON, so override the shared JSON Accept header
# to keep a strict server from returning 406.
_HTML_HEADERS = {**_HEADERS, "Accept": "text/html,application/xhtml+xml"}

_ANCHOR = "const portfolioJobs"

_HOURS_PER_YEAR = 2080  # 40h x 52 weeks, standard annualization factor


def _fetch_board_html(url: str) -> str:
    """GET a Consider board page; '' on any failure (never raises)."""
    try:
        resp = requests.get(url, headers=_HTML_HEADERS, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Consider board %s returned %s", url, resp.status_code)
            return ""
        return resp.text
    except requests.RequestException as exc:
        logger.warning("Consider fetch failed (%s): %s", url, exc)
        return ""


def _extract_portfolio_jobs(html: str) -> list[dict]:
    """Pull the ``const portfolioJobs = [...]`` array out of the board HTML.

    A regex can't reliably span the nested/escaped JSON, so we locate the
    opening ``[`` and walk forward tracking bracket depth and string state
    until the array closes, then ``json.loads`` the slice. Returns [] on any
    malformed input so the scraper degrades gracefully.
    """
    idx = html.find(_ANCHOR)
    if idx == -1:
        return []
    eq = html.find("=", idx)
    if eq == -1:
        return []
    i = eq + 1
    while i < len(html) and html[i] in " \t\r\n":
        i += 1
    if i >= len(html) or html[i] != "[":
        return []

    depth = 0
    in_str = False
    esc = False
    end = -1
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
    if end == -1:
        return []

    try:
        data = json.loads(html[i:end])
    except ValueError as exc:
        logger.warning("Consider: could not parse portfolioJobs JSON: %s", exc)
        return []
    return data if isinstance(data, list) else []


def _iter_jobs(groups: list[dict]):
    """Yield ``(job, group_company)`` pairs from the company-grouped array."""
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_company = group.get("company")
        jobs = group.get("jobs")
        if not isinstance(jobs, list):
            continue
        for job in jobs:
            if isinstance(job, dict):
                yield job, group_company


def _annualize(amount: object, period: object) -> float | None:
    """Normalize a salary figure to whole annual dollars, or None.

    Consider reports pay as ``{minValue, maxValue, period}`` where period is
    "Year" (already annual), "Hour", "Week", "Month", or "Day". Values are
    plain dollars, not cents.
    """
    if amount is None:
        return None
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return None
    p = str(period or "").lower()
    if p.startswith("hour"):
        return val * _HOURS_PER_YEAR
    if p.startswith("day"):
        return val * 260  # ~52 * 5 working days
    if p.startswith("week"):
        return val * 52
    if p.startswith("month"):
        return val * 12
    return val  # "Year" or unknown, treat as already annual


def _normalize_job(job: dict, group_company: object, *, is_crypto: bool = True) -> dict:
    """Map one Consider board job to our standard scraper dict."""
    title = str(job.get("title") or "").strip()
    company = str(job.get("companyName") or group_company or "").strip()
    url = str(job.get("url") or "").strip()

    is_remote = bool(job.get("remote"))

    raw_locations = job.get("locations") or []
    locs = (
        [str(loc).strip() for loc in raw_locations if loc and str(loc).strip()]
        if isinstance(raw_locations, list)
        else []
    )
    if locs:
        # Consider often lists both a full and an abbreviated form
        # ("New York City, New York, United States" + "New York City"). The
        # longest is the most specific.
        location = max(locs, key=len)
    else:
        location = "Remote" if is_remote else "Not specified"

    # No description body in the payload, so surface the structured signals
    # so keyword scoring has domain-relevant text to work with.
    parts: list[str] = []
    for label, key in (("Seniority", "seniorities"), ("Function", "functions"), ("Skills", "skills")):
        vals = job.get(key) or []
        if isinstance(vals, list):
            joined = ", ".join(v for v in vals if isinstance(v, str) and v)
            if joined:
                parts.append(f"{label}: {joined}")
    description = _strip_html("\n".join(parts))

    salary = job.get("salary") if isinstance(job.get("salary"), dict) else {}
    period = salary.get("period")
    sal_min = _annualize(salary.get("minValue"), period)
    sal_max = _annualize(salary.get("maxValue"), period)

    normalized: dict = {
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": "consider",
        "description": description,
        "salary_min": sal_min,
        "salary_max": sal_max,
        "date_posted": job.get("createdAt") or "",
        "is_remote": is_remote,
        # Consider carries a definitive remote bool, so mark it reported and
        # finalize won't downgrade work-type confidence to "inferred".
        "remote_flag_reported": True,
        "company_size": "",
    }
    if is_crypto:
        # Flag crypto-board jobs so the pipeline's DB purge applies the same
        # crypto-aware role matching the scrape used, and doesn't later drop a
        # kept "Solidity Engineer" that doesn't word-match the user's roles.
        normalized["crypto"] = True
    return normalized


@register_scraper(
    name="consider",
    display_name="Consider (a16z + VC networks)",
    url="https://consider.com",
    description="VC talent-network jobs (a16z crypto portfolio + others) via Consider boards",
    category="crypto",
    # Opt-in like getro/cryptojobslist. Crypto-domain listings are noise for a
    # non-crypto search, so profiles enable it explicitly in config.
    enabled_by_default=False,
)
def search_consider(
    roles: list[str] | None = None,
    max_results: int = 50,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Fetch VC-network jobs from Consider-powered board pages.

    For each seed board: fetch the HTML, extract the embedded ``portfolioJobs``
    array, flatten the company groups, and normalize until ``max_results`` is
    satisfied. Crypto boards (a16z crypto) use :func:`_match_roles_crypto` so
    web3 titles ("Solidity Engineer", "ZK Researcher") pass even when they don't
    word-match the user's normal target roles.
    """
    logger.info("Fetching jobs from Consider talent-network boards...")
    results: list[dict] = []
    seen: set[str] = set()

    for slug, board_url, is_crypto in _CONSIDER_BOARDS:
        if len(results) >= max_results:
            break
        html = _fetch_board_html(board_url)
        if not html:
            continue
        groups = _extract_portfolio_jobs(html)
        match_fn = _match_roles_crypto if is_crypto else _match_roles

        for job, group_company in _iter_jobs(groups):
            if len(results) >= max_results:
                break
            normalized = _normalize_job(job, group_company, is_crypto=is_crypto)
            if not normalized["title"]:
                continue
            key = normalized["url"] or f"{normalized['title']}|{normalized['company']}"
            if key in seen:
                continue
            if roles and not match_fn(
                normalized["title"],
                roles,
                match_mode=match_mode,
                include_founding=include_founding,
            ):
                continue
            results.append(normalized)
            seen.add(key)

    logger.info("Consider: found %d matching jobs", len(results))
    return results
