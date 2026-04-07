"""Watchlist service — company ATS discovery and profile storage."""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_TIMEOUT = 5


def _generate_slugs(company_name: str) -> list[str]:
    """Generate possible ATS board slugs from a company name."""
    name = company_name.strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)
    parts = name.split()
    if not parts:
        return []

    slugs: list[str] = []
    hyphenated = "-".join(parts)
    joined = "".join(parts)

    # Most likely first
    slugs.append(hyphenated)
    if joined != hyphenated:
        slugs.append(joined)

    # First word only (e.g. "Anduril Industries" → "anduril")
    if len(parts) > 1:
        slugs.append(parts[0])

    # Common suffixes
    for base in [hyphenated, joined]:
        for suffix in ["inc", "hq", "io", "ai", "jobs"]:
            slugs.append(f"{base}{suffix}")
            if "-" not in base or suffix not in base:
                slugs.append(f"{base}-{suffix}")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def _try_greenhouse(slug: str) -> dict | None:
    """Check if company has a Greenhouse board. Returns metadata or None."""
    try:
        resp = requests.get(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobs", [])
            if isinstance(jobs, list):
                return {
                    "ats": "greenhouse",
                    "slug": slug,
                    "job_count": len(jobs),
                    "careers_url": f"https://boards.greenhouse.io/{slug}",
                }
    except Exception:
        pass
    return None


def _try_lever(slug: str) -> dict | None:
    """Check if company has a Lever board. Returns metadata or None."""
    try:
        resp = requests.get(
            f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                # Need a second request for total count (or just report 1+)
                count_resp = requests.get(
                    f"https://api.lever.co/v0/postings/{slug}?mode=json",
                    timeout=_TIMEOUT,
                )
                total = len(count_resp.json()) if count_resp.status_code == 200 else len(data)
                return {
                    "ats": "lever",
                    "slug": slug,
                    "job_count": total,
                    "careers_url": f"https://jobs.lever.co/{slug}",
                }
    except Exception:
        pass
    return None


def _try_ashby(slug: str) -> dict | None:
    """Check if company has an Ashby board. Returns metadata or None."""
    try:
        resp = requests.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            jobs = data.get("jobs", [])
            if isinstance(jobs, list):
                return {
                    "ats": "ashby",
                    "slug": slug,
                    "job_count": len(jobs),
                    "careers_url": f"https://jobs.ashbyhq.com/{slug}",
                }
    except Exception:
        pass
    return None


def discover_company(name: str) -> dict:
    """Auto-detect a company's ATS and board slug.

    Tries Greenhouse, Lever, and Ashby with generated slug variations.
    Returns a dict with name, slug, ats, job_count, careers_url.
    """
    slugs = _generate_slugs(name)
    if not slugs:
        return {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""}

    # Try each ATS in parallel for the most likely slug first, then expand
    ats_fns = [_try_greenhouse, _try_lever, _try_ashby]

    # Fast path: try the first slug on all ATS platforms simultaneously
    with ThreadPoolExecutor(max_workers=3) as pool:
        for slug in slugs[:3]:  # Try top 3 most likely slugs
            futures = {pool.submit(fn, slug): fn.__name__ for fn in ats_fns}
            for future in futures:
                result = future.result()
                if result:
                    return {"name": name, **result}

    # Slower path: try remaining slug variations
    for slug in slugs[3:]:
        for fn in ats_fns:
            result = fn(slug)
            if result:
                return {"name": name, **result}

    return {"name": name, "slug": slugs[0], "ats": "unknown", "job_count": 0, "careers_url": ""}


def build_watchlist_entries(company_names: list[str]) -> list[dict]:
    """Discover ATS-backed watchlist entries for a list of company names.

    Only confirmed ATS boards are returned. Unknown/unconfirmed companies are
    skipped so the scraper layer does not spray guessed slugs across every ATS.
    """
    cleaned_names: list[str] = []
    seen: set[str] = set()
    for name in company_names:
        normalized = name.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned_names.append(normalized)

    if not cleaned_names:
        return []

    results_by_name: dict[str, dict] = {}
    workers = min(len(cleaned_names), 6)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(discover_company, name): name for name in cleaned_names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception:
                logger.debug("ATS discovery failed for %s", name, exc_info=True)
                continue
            if not result:
                continue
            if result.get("ats") == "unknown" or not result.get("slug"):
                continue
            results_by_name[name.lower()] = result

    return [results_by_name[name.lower()] for name in cleaned_names if name.lower() in results_by_name]


def _get_profile_path(profile: str) -> str:
    """Resolve the YAML file path for a profile."""
    config_dir = os.path.join(_PROJECT_ROOT, "src", "job_finder", "config", "profiles")
    name = profile if profile != "default" else "default"
    return os.path.join(config_dir, f"{name}.yaml")


def _load_profile_yaml(profile: str) -> dict:
    """Load profile YAML, falling back to template if needed."""
    path = _get_profile_path(profile)
    config_dir = os.path.dirname(path)
    template_path = os.path.join(config_dir, "_template.yaml")

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    elif os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_profile_yaml(profile: str, cfg: dict) -> None:
    """Write profile YAML back to disk."""
    path = _get_profile_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def get_watchlist(profile: str) -> dict:
    """Get the company watchlist for a profile."""
    cfg = _load_profile_yaml(profile)
    companies = cfg.get("watchlist", [])
    return {"profile": profile, "companies": companies}


def add_company(profile: str, name: str) -> dict:
    """Add a company to the watchlist with ATS auto-discovery.

    Returns the updated watchlist.
    """
    cfg = _load_profile_yaml(profile)
    watchlist = cfg.get("watchlist", [])

    # Check if already exists
    normalized = name.strip().lower()
    for entry in watchlist:
        if entry.get("name", "").lower() == normalized:
            return {"profile": profile, "companies": watchlist}

    # Discover ATS
    logger.info("Discovering ATS for company: %s", name)
    result = discover_company(name)

    watchlist.append(result)
    cfg["watchlist"] = watchlist
    _save_profile_yaml(profile, cfg)

    return {"profile": profile, "companies": watchlist}


def remove_company(profile: str, name: str) -> dict:
    """Remove a company from the watchlist."""
    cfg = _load_profile_yaml(profile)
    watchlist = cfg.get("watchlist", [])

    normalized = name.strip().lower()
    watchlist = [c for c in watchlist if c.get("name", "").lower() != normalized]

    cfg["watchlist"] = watchlist
    _save_profile_yaml(profile, cfg)

    return {"profile": profile, "companies": watchlist}
