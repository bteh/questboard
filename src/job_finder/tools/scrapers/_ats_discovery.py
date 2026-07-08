"""Dynamic ATS company-slug discovery.

The ATS scrapers (Ashby, Greenhouse, Lever) previously relied on hand-curated
seed lists in ``data/<host>_seed.txt`` plus the user's "Target Companies"
watchlist. That capped coverage at ~160 companies. Small employers (e.g.
3-person Ashby teams) never surfaced because nobody added them to the seed.

This module fills that gap by querying DuckDuckGo (via the ``ddgs`` library,
already a project dependency) for ``site:<ats-host> "<role>"`` for each of the
user's target roles, harvesting company slugs from result URLs via per-host
regex, and persisting them to a JSON cache with a 7-day TTL.

The cache lives at ``data/cache/ats_discovered_<host>.json`` and is unioned
each run — the discovered slug list only grows. ``run_scrapers`` calls
``discover_and_cache`` before launching each ATS scraper; discovered slugs
flow into the existing ``watchlist_companies`` kwarg, merging with seed +
user watchlist inside each scraper.

Discovery is best-effort: a DDG failure (rate limit, network, parser drift)
logs a warning and returns whatever's currently cached. ATS scrapers still
run on their seed list even when discovery breaks.

Disable via ``QUESTBOARD_DISABLE_ATS_DISCOVERY=1`` if you ever need to.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Per-ATS host config. ``domain`` is the value plugged into the
# ``site:<domain>`` DDG query operator. ``slug_re`` extracts the company
# slug from a result URL — the first capture group is the slug.
ATS_HOSTS: dict[str, dict[str, Any]] = {
    "ashby": {
        "domain": "jobs.ashbyhq.com",
        "slug_re": re.compile(
            r"^https?://jobs\.ashbyhq\.com/([^/?#]+)",
            re.IGNORECASE,
        ),
    },
    "greenhouse": {
        "domain": "boards.greenhouse.io",
        # Matches both legacy boards.greenhouse.io/<slug>/jobs/<id> URLs and
        # the embed variant boards.greenhouse.io/embed/job_app?for=<slug>.
        "slug_re": re.compile(
            r"^https?://(?:boards|job-boards)\.greenhouse\.io/"
            r"(?:embed/job_app\?for=)?([^/?&#]+)",
            re.IGNORECASE,
        ),
    },
    "lever": {
        "domain": "jobs.lever.co",
        "slug_re": re.compile(
            r"^https?://jobs\.lever\.co/([^/?#]+)",
            re.IGNORECASE,
        ),
    },
    "workable": {
        "domain": "apply.workable.com",
        # https://apply.workable.com/<slug>/... — the first path segment is
        # the account slug. Endpoint-only segments (j, jobs, view, api, …) are
        # rejected by _SLUG_BLOCKLIST below.
        "slug_re": re.compile(
            r"^https?://apply\.workable\.com/([^/?#]+)",
            re.IGNORECASE,
        ),
    },
}

CACHE_TTL_DAYS = 7
CACHE_VERSION = 1
_CACHE_DIR = Path(__file__).parent / "data" / "cache"

# Slug values that some result URLs legitimately have but aren't valid
# ATS boards (e.g. the ATS's own marketing pages).
_SLUG_BLOCKLIST = {
    "embed",
    "job_app",
    "jobs",
    "careers",
    "about",
    "pricing",
    "login",
    "signup",
    "blog",
    "help",
    "support",
    "api",
    "docs",
    # Workable non-account path segments (apply.workable.com/j/<id>, etc.)
    "j",
    "view",
    "spi",
    "widget",
    "accounts",
    "backend",
    "whoami",
}


def _cache_path(host: str) -> Path:
    return _CACHE_DIR / f"ats_discovered_{host}.json"


def _discovery_disabled() -> bool:
    return os.environ.get("QUESTBOARD_DISABLE_ATS_DISCOVERY", "").strip().lower() in {"1", "true", "yes"}


def extract_slug(host: str, url: str) -> str | None:
    """Extract the company slug from a result URL for the given ATS host.

    Returns ``None`` when the URL doesn't match the host's pattern, when the
    captured slug is in the blocklist (e.g. ``embed`` for Greenhouse), or
    when the slug looks malformed (empty, contains whitespace, etc.).
    """
    cfg = ATS_HOSTS.get(host)
    if not cfg:
        return None
    m = cfg["slug_re"].match(url or "")
    if not m:
        return None
    slug = m.group(1).strip().lower()
    if not slug or any(ch.isspace() for ch in slug):
        return None
    if slug in _SLUG_BLOCKLIST:
        return None
    # Trim trailing punctuation that sometimes ends up in URLs.
    slug = slug.rstrip(".,;:!?")
    return slug or None


def load_cached_slugs(host: str) -> tuple[set[str], bool]:
    """Load cached slugs and report freshness.

    Returns ``(slugs, is_fresh)``. Stale slugs are still returned — the
    caller decides whether to refresh, but graceful degradation means we
    always have *something* even if DDG breaks.
    """
    path = _cache_path(host)
    if not path.exists():
        return set(), False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ATS discovery cache for %s unreadable, ignoring: %s", host, exc)
        return set(), False

    slugs_raw = payload.get("slugs") or []
    slugs = {str(s).strip().lower() for s in slugs_raw if s}
    discovered_at_raw = payload.get("discovered_at") or ""
    try:
        discovered_at = datetime.fromisoformat(discovered_at_raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return slugs, False
    is_fresh = (datetime.now(timezone.utc) - discovered_at) < timedelta(days=CACHE_TTL_DAYS)
    return slugs, is_fresh


def save_discovered_slugs(host: str, slugs: set[str]) -> None:
    """Persist slugs to the cache file atomically."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "host": host,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "slugs": sorted(slugs),
    }
    path = _cache_path(host)
    # Atomic write: tmp file in same dir, then rename.
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as tmp:
        json.dump(payload, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


# Cap how many roles each host fans out to DuckDuckGo. The AI role expansion
# produces 10-20 roles; querying all of them ×3 ATS hosts means ~60 serial DDG
# calls on a cold cache before any ATS scraper returns. The first few
# (most-relevant) roles already harvest plenty of slugs, and results union with
# the 7-day cache across runs, so a tight cap mainly bounds cold-start latency.
_MAX_DISCOVERY_ROLES = 6


def discover_slugs(
    host: str,
    roles: list[str],
    max_per_role: int = 10,
    max_roles: int = _MAX_DISCOVERY_ROLES,
) -> set[str]:
    """Query DuckDuckGo for ATS company URLs matching each role and harvest slugs.

    Only the first ``max_roles`` roles are searched (cold-start latency cap).
    Returns the union of all extracted slugs. Catches every exception so a
    DDG outage never blocks the caller; the partial harvest is returned.
    """
    cfg = ATS_HOSTS.get(host)
    if not cfg or not roles:
        return set()

    search_roles = roles[:max_roles]
    if len(roles) > len(search_roles):
        logger.info(
            "ATS discovery (%s): searching %d of %d roles (cold-start cap)",
            host, len(search_roles), len(roles),
        )

    domain = cfg["domain"]
    found: set[str] = set()
    try:
        from ddgs import DDGS  # imported lazily so unit tests can patch it
    except ImportError as exc:
        logger.warning("ddgs library missing — ATS discovery disabled: %s", exc)
        return set()

    for role in search_roles:
        role_clean = (role or "").strip()
        if not role_clean:
            continue
        query = f'site:{domain} "{role_clean}"'
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=max_per_role)
        except Exception as exc:
            # DDG can rate-limit, time out, or return malformed HTML when
            # they redesign their results page. Log + move on with whatever
            # we've collected so far.
            logger.warning("DDG search for %s/%s failed (non-fatal): %s", host, role_clean, exc)
            continue
        for item in results or []:
            url = item.get("href") or item.get("url") or ""
            slug = extract_slug(host, url)
            if slug:
                found.add(slug)
    return found


def discover_and_cache(host: str, roles: list[str]) -> set[str]:
    """Top-level entry point: cache-first slug discovery.

    Behavior:
      - If the cache is fresh (< TTL), return cached slugs without hitting DDG.
      - If stale or missing, query DDG, union with any cached slugs (so we
        never lose previously-discovered companies), persist, and return.
      - If DDG fails, return whatever's cached (stale slugs are better than
        none).
      - If discovery is disabled via env var, return cached slugs only.
    """
    if host not in ATS_HOSTS:
        return set()
    cached, is_fresh = load_cached_slugs(host)
    if _discovery_disabled():
        return cached
    if is_fresh:
        return cached
    if not roles:
        # No roles to search for — return whatever we have without refreshing.
        return cached

    discovered = discover_slugs(host, roles)
    union = cached | discovered
    # Only persist if discovery actually contributed something new OR cache
    # was previously missing — avoids touching disk on every search when
    # DDG hands us the same slugs we already had.
    if discovered or not cached:
        try:
            save_discovered_slugs(host, union)
        except OSError as exc:
            logger.warning("Failed to persist ATS discovery cache for %s: %s", host, exc)
    return union
