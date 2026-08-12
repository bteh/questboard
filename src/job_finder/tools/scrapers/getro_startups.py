"""Getro Community, a broad index of VC portfolio job boards.

Questboard already searches two crypto-specific Getro collections. Getro's
public Community collection is a separate, much broader pool across VC and
accelerator portfolios. Querying it by the seeker's role families adds early-
stage and founding jobs without crawling each fund's branded board.
"""

from __future__ import annotations

import logging
import re

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _match_roles, rank_by_relevance
from job_finder.tools.scrapers.getro import _fetch_search, _normalize_job

logger = logging.getLogger(__name__)

_COMMUNITY_COLLECTION_ID = 8870
# Techstars' official Getro board currently carries thousands of openings and
# is especially valuable for companies that never appear in hand-maintained ATS
# seeds. Community remains the broad cross-fund lane; Techstars is additive.
_STARTUP_COLLECTIONS: list[tuple[str, int]] = [
    ("community", _COMMUNITY_COLLECTION_ID),
    ("techstars", 89),
]
_PAGE_SIZE = 20
_MAX_PAGES_PER_QUERY = 4
_MAX_QUERIES = 6

_PREFIX_RE = re.compile(
    r"^(?:senior\s+manager|senior|staff|principal|lead|director(?:\s+of)?|"
    r"manager(?:\s+of)?|head\s+of|vp(?:\s+of)?|founding)\s+",
    re.IGNORECASE,
)


def _canonical_query(role: str) -> str:
    """Collapse seniority variants into a useful Getro keyword query."""
    value = re.sub(r"\s+", " ", role.strip().lower())
    while value and _PREFIX_RE.match(value):
        value = _PREFIX_RE.sub("", value, count=1).strip(" ,-_")
    words = set(re.findall(r"[a-z0-9]+", value))
    if "data" in words and words & {"engineer", "engineering"}:
        return "data engineer"
    if "analytics" in words and words & {"engineer", "engineering"}:
        return "analytics engineer"
    if "data" in words and "platform" in words:
        return "data platform"
    if "data" in words and "infrastructure" in words:
        return "data infrastructure"
    if "data" in words and "governance" in words:
        return "data governance"
    if "bi" in words and words & {"engineer", "engineering"}:
        return "bi engineer"
    return value


def _search_queries(roles: list[str] | None) -> list[str]:
    """Small, deterministic query set with founding variants first."""
    bases: list[str] = []
    seen: set[str] = set()
    for role in roles or []:
        query = _canonical_query(str(role))
        if not query or query in seen:
            continue
        seen.add(query)
        bases.append(query)

    founding = [
        f"founding {query}"
        for query in bases
        if "engineer" in query
    ][:2]
    ordered = founding + bases
    return list(dict.fromkeys(ordered))[:_MAX_QUERIES]


@register_scraper(
    name="getro_startups",
    display_name="Getro VC portfolios",
    url="https://community.getro.com/jobs",
    description="Early-stage and founding roles across VC portfolio job boards",
    # The Community collection includes seed companies, late-stage portfolio
    # companies, and a few fund/operator roles. Keep it separate from YC's
    # startup-only shelf so source provenance never guesses company stage.
    category="vc",
    enabled_by_default=True,
)
def search_getro_startups(
    roles: list[str] | None = None,
    max_results: int = 200,
    match_mode: str = "all_significant",
    include_founding: bool = True,
    **kwargs,
) -> list[dict]:
    """Search the Community collection by role family.

    Getro's query search is intentionally broad, so the local title matcher
    remains strict at this source boundary. A founding data job still matches
    the saved Data Engineer family, while unrelated founding software roles do
    not enter the pipeline merely because they share the word "founding".
    The pipeline's later location, compensation, and title gates still apply.
    """
    queries = _search_queries(roles)
    if not queries:
        return []

    limit = max(1, min(int(max_results or 200), 300))
    results: list[dict] = []
    seen: set[str] = set()

    for query in queries:
        exhausted: set[int] = set()
        for page in range(_MAX_PAGES_PER_QUERY):
            page_had_rows = False
            for collection_slug, collection_id in _STARTUP_COLLECTIONS:
                if collection_id in exhausted:
                    continue
                raw_jobs = _fetch_search(collection_id, page, query=query)
                if not raw_jobs:
                    exhausted.add(collection_id)
                    continue
                page_had_rows = True
                for raw in raw_jobs:
                    if not isinstance(raw, dict):
                        continue
                    job = _normalize_job(raw)
                    job["source"] = "getro_startups"
                    job["network"] = collection_slug
                    if not job.get("title") or not job.get("url"):
                        continue
                    if roles and not _match_roles(
                        job["title"],
                        roles,
                        # Broad API results need a precise profession boundary.
                        match_mode="all_significant",
                        include_founding=False,
                    ):
                        continue
                    key = str(job["url"])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(job)
                # A short page exhausts only this collection, not its peer.
                if len(raw_jobs) < _PAGE_SIZE:
                    exhausted.add(collection_id)
            if not page_had_rows or len(exhausted) == len(_STARTUP_COLLECTIONS):
                break

    results = rank_by_relevance(results, roles)[:limit]
    logger.info(
        "Getro VC portfolios: found %d matching jobs across %d role queries and %d networks",
        len(results),
        len(queries),
        len(_STARTUP_COLLECTIONS),
    )
    return results
