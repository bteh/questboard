"""Job-search pipeline — framework-free orchestration.

Replaces the CrewAI crew with a simple Python pipeline.
LLM features are *optional*: search, track and basic scoring work with
zero LLM configuration.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import yaml

from job_finder.llm_client import LLMClient
from job_finder.models.database import (
    init_db,
    save_application,
    update_application_status,
)
from job_finder.prompts import (
    COMPANY_RESEARCHER_USER_TEMPLATE,
    COMPANY_RESEARCHER_GROUNDED_USER_TEMPLATE,
    COVER_LETTER_USER_TEMPLATE,
    EVALUATION_REPORT_USER_TEMPLATE,
    GENERATE_PROFILE_USER_TEMPLATE,
    JD_SCORER_USER_TEMPLATE,
    RESUME_OPTIMIZER_USER_TEMPLATE,
    _wrap_untrusted,
    build_company_researcher_prompt,
    build_cover_letter_prompt,
    build_evaluation_report_prompt,
    build_generate_profile_prompt,
    build_resume_optimizer_prompt,
    build_scorer_prompt,
)
from job_finder.company_classifier import (
    classify_company,
    classify_job_work_type,
    classify_work_type,  # noqa: F401 — re-export for existing consumers
    location_matches_preferences,
)
from job_finder.scoring import score_job_basic, get_company_baselines, normalize_company_key
from job_finder.scoring.dimensions import (
    _extract_level,
    resolve_current_level,
)  # re-export for tests/consumers
from job_finder.scoring.helpers import annualize_amount
from job_finder.scoring.score_cache import cache_key as ai_score_cache_key
from job_finder.scoring.score_cache import load_cached as load_cached_ai_score
from job_finder.scoring.score_cache import save_cached as save_cached_ai_score
from job_finder.staffing import STAFFING_AGENCY_NAMES, is_staffing_agency
from job_finder.tools.job_search_tool import search_jobs
from job_finder.tools.resume_parser_tool import find_resume, parse_resume

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_SAFE_PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_config(config: dict, source: str) -> dict:
    """Run Pydantic profile validation and log any issues.

    Always returns the original *config* dict so the pipeline keeps working
    even if validation finds problems (graceful degradation).
    """
    try:
        from job_finder.config.profile_schema import validate_profile_safe

        _profile, errors = validate_profile_safe(config)
        if _profile is None:
            for err in errors:
                logger.warning("Profile validation error (%s): %s", source, err)
        elif errors:
            for err in errors:
                logger.warning("Profile validation warning (%s): %s", source, err)
        else:
            logger.debug("Profile validated successfully (%s)", source)
    except Exception:  # noqa: BLE001
        logger.debug("Profile validation unavailable, skipping", exc_info=True)
    return config


def _load_search_config(profile: str | None = None) -> dict:
    """Load config for the given profile.

    Prefers ``config/profiles/default.yaml`` for the default profile so the
    runtime uses the real editable default profile instead of the legacy sample
    search config. Falls back to ``config/search_config.yaml`` only when no
    profile file exists.
    """
    config_dir = os.path.join(os.path.dirname(__file__), "config")
    profiles_dir = os.path.join(config_dir, "profiles")

    if profile and not _SAFE_PROFILE_RE.fullmatch(profile):
        logger.warning("Ignoring unsafe profile name '%s'; using default config", profile)
        profile = None

    if profile == "default" or not profile:
        profile_path = os.path.join(profiles_dir, "default.yaml")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return _validate_config(config, profile_path)

    if profile and profile != "default":
        profile_path = os.path.join(profiles_dir, f"{profile}.yaml")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return _validate_config(config, profile_path)
        logger.warning("Profile '%s' not found, using default config", profile)

    # Fallback: original search_config.yaml
    config_path = os.path.join(config_dir, "search_config.yaml")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return _validate_config(config, config_path)


# Dedup primitives live in job_finder.dedup so the pipeline, the post-run DB
# merge (backend pipeline_service), and the startup data repair (models.
# maintenance) share ONE definition of "duplicate". The underscore aliases
# keep this module's long-standing import surface for existing consumers.
from job_finder.dedup import (
    cluster_jobs as _cluster_jobs,
    describe_collapse as _describe_collapse,
    descriptions_look_duplicate as _descriptions_look_duplicate,
    loc_is_remote as _loc_is_remote,
    locations_compatible as _locations_compatible,
    normalize_company as _normalize_company,
    normalize_description as _normalize_description,
    normalize_location as _normalize_location,
    normalize_title as _normalize_title,
    richness_key as _dedup_richness_key,
    same_posting as _same_posting,
    short_or_empty_description as _short_or_empty_description,
)


def _dedup_key(company: str, title: str, location: str = "") -> str:
    """Create a normalized key for cautious fuzzy dedup."""
    return "||".join((
        _normalize_company(company),
        _normalize_title(title),
        _normalize_location(location),
    ))


# -- Seniority / management prefixes used for search-term consolidation ------

_SENIORITY_PREFIXES = [
    "head of",
    "senior manager",
    "senior",
    "staff",
    "principal",
    "lead",
    "junior",
    "founding",
]

_MANAGEMENT_PREFIXES = [
    "vp of",
    "vp",
    "director of",
    "director",
    "manager",
]

# Terms that are niche enough to keep even when a broader base-role query exists.
# Matches "founding <anything>" and "first <role> hire" for ALL professions.
_HIGH_VALUE_PATTERNS = re.compile(
    r"\b(founding\s+\w+|first\s+\w+\s+hire|head\s+of\s+\w+)\b",
    re.IGNORECASE,
)

# Short specialty keywords that should never be merged away.
# These are tools, technologies, and domain terms across industries that
# represent distinct search intent.  Profiles can add their own via
# keyword_searches and keywords.technical.
_DEFAULT_SPECIALTY_KEYWORDS = {
    # Common short terms across many fields
    "sql", "python", "java", "aws", "gcp", "azure",
    "react", "vue", "angular", "docker", "terraform",
    "figma", "sketch", "emr", "ehr", "epic", "seo",
}


# Tokens that make a term look like a JOB TITLE worth searching boards for.
# A keyword carrying none of these (e.g. "rbac", "mcp", "sox compliance",
# "pii masking", "federated query", "semantic layer", "apache iceberg") is a
# SKILL — it belongs in scoring/ranking, NOT as a board job-title query, where
# it just returns noise and burns the board's limited query budget.
_ROLE_TYPE_TOKENS = frozenset({
    "engineer", "engineering", "developer", "dev", "manager", "director",
    "analyst", "scientist", "architect", "lead", "head", "vp", "principal",
    "staff", "officer", "president", "founder", "administrator", "specialist",
    "consultant", "designer", "coordinator", "strategist", "practitioner",
    "nurse", "accountant", "recruiter", "researcher",
})
_DOMAIN_TITLE_TOKENS = frozenset({
    "data", "platform", "analytics", "infrastructure", "ml", "ai", "software",
    "security", "devops", "cloud", "backend", "frontend", "fullstack",
    "product", "marketing", "sales", "design", "finance", "operations",
    "research", "mobile", "web", "machine", "learning", "systems", "network",
    "database", "reliability", "sre",
})


def _is_searchable_title(term: str, *, extra_tokens: frozenset[str] | set[str] = frozenset()) -> bool:
    """True if a term is shaped like a job title worth searching boards for.

    Role titles ("Lead Data Engineer") and title-shaped domain phrases ("data
    platform", "data mesh", "analytics engineering") qualify. Pure skills,
    tools, and acronyms ("rbac", "mcp", "dbt", "sox compliance", "pii masking",
    "federated query", "semantic layer", "apache iceberg", "trino") do NOT —
    searching those as job TITLES returns noise; they belong in scoring.

    The hardcoded token sets are tech-biased, so callers can pass
    ``extra_tokens`` harvested from the user's own profile (see
    :func:`_profile_title_tokens`) — a nurse's "APRN" must not be dropped
    just because nursing vocabulary isn't in the builtin sets. Every dropped
    term is logged at INFO so silent misses are visible in the run log.
    """
    if not term or not term.strip():
        return False
    words = set(re.findall(r"[a-z0-9]+", term.lower()))
    if words & _ROLE_TYPE_TOKENS or words & _DOMAIN_TITLE_TOKENS:
        return True
    if extra_tokens and words & extra_tokens:
        return True
    logger.info(
        "Search term %r dropped: not title-shaped (skills drive scoring, not board queries)",
        term,
    )
    return False


def _profile_title_tokens(config: dict | None) -> frozenset[str]:
    """Title vocabulary harvested from the user's own profile.

    ``target_roles`` are titles by definition, so their tokens always count.
    When those roles hit none of the hardcoded domain tokens, the profile's
    field is one the builtin (tech-biased) sets don't know — the skill-vs-
    title split can't be trusted there, so tokens from the user's own
    ``keyword_searches`` and resume-extracted ``keywords.technical`` count
    as title vocabulary too (permissive). Tech-domain profiles keep the
    strict split so "rbac"/"dbt" never become board queries.
    """
    if not config:
        return frozenset()
    tokens: set[str] = set()
    for term in config.get("target_roles", []) or []:
        tokens.update(re.findall(r"[a-z0-9]+", str(term).lower()))
    if not tokens & _DOMAIN_TITLE_TOKENS:
        keywords_cfg = config.get("keywords") or {}
        harvest = list(config.get("keyword_searches", []) or [])
        harvest.extend(keywords_cfg.get("technical", []) or [])
        for term in harvest:
            tokens.update(re.findall(r"[a-z0-9]+", str(term).lower()))
    return frozenset(tokens)


def _build_search_terms(
    config: dict | None,
    roles: list[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Assemble the consolidated board-query list for a profile.

    Returns ``(consolidated_terms, roles_raw, keywords_raw)``. When *roles*
    is passed explicitly (the API path — keywords already merged into it),
    ``keyword_searches`` is NOT re-read (double-count), but title-shaped
    resume skills from ``keywords.technical`` still merge in: they were
    previously used only for scoring and never reached search queries.
    """
    config = config or {}
    profile_tokens = _profile_title_tokens(config)
    if roles:
        roles_raw = list(roles)
        keywords_raw: list[str] = []
    else:
        roles_raw = list(config.get("target_roles", []) or [])
        # Only search title-shaped keywords as board queries; pure skills
        # ("rbac", "dbt", "sox compliance") stay for scoring, not title search.
        keywords_raw = [
            k for k in config.get("keyword_searches", []) or []
            if _is_searchable_title(k, extra_tokens=profile_tokens)
        ]

    # Merge title-shaped resume skills (dedup case-insensitively against
    # terms already present).
    seen = {str(t).strip().lower() for t in roles_raw + keywords_raw if str(t).strip()}
    keywords_cfg = config.get("keywords") or {}
    for skill in keywords_cfg.get("technical", []) or []:
        s = str(skill).strip()
        if not s or s.lower() in seen:
            continue
        if _is_searchable_title(s, extra_tokens=profile_tokens):
            keywords_raw.append(s)
            seen.add(s.lower())

    consolidated = _consolidate_search_terms(roles_raw, keywords_raw, config=config)
    return consolidated, roles_raw, keywords_raw


def _search_query_priority(term: str, specialty_kw: set[str]) -> int:
    """Ordering key for board search queries (lower runs first).

    Real job TITLES run before niche/skill terms so the user's core role
    searches aren't starved when a board's circuit breaker trips (rate limit /
    CAPTCHA) partway through a run.
    """
    t = term.lower()
    words = set(re.findall(r"[a-z0-9]+", t))
    if words & _ROLE_TYPE_TOKENS:
        return 0  # actual job titles first ("data engineer", "lead data platform")
    if _HIGH_VALUE_PATTERNS.search(term):
        return 1  # founding / head-of niche roles
    if words & _DOMAIN_TITLE_TOKENS:
        return 2  # domain title phrases ("data platform", "data mesh")
    if t in specialty_kw or len(t) <= 4:
        return 3  # short tech keywords
    return 4  # everything else last


def _build_jobspy_tasks(
    search_tasks: list[tuple[str, str]],
    boards: list[str] | None,
) -> list[tuple[str, str, list[str] | None]]:
    """Expand role/location searches into independently isolated board calls.

    JobSpy already starts one worker per board internally, but it does not
    return until *every* board in that call finishes. One slow board therefore
    used to discard a healthy board's completed rows when the shared 45-second
    deadline fired. Explicit board lists are split here so each board keeps the
    same query coverage and concurrency while succeeding, timing out, and
    tripping its circuit breaker independently.

    ``None`` preserves JobSpy's default-board behavior for legacy callers. An
    explicit empty list remains a real opt-out and creates no work.
    """
    if boards is None:
        return [(term, location, None) for term, location in search_tasks]
    return [
        (term, location, [board])
        for term, location in search_tasks
        for board in boards
    ]


def _scaled_results_per_board(base: int, original_terms: int, consolidated_terms: int) -> int:
    """Preserve approximate total recall after query consolidation.

    Scale proportionally. The old ``max(2, int(ratio))`` doubled every query
    after removing even one duplicate (18 titles -> 17 queries requested 100
    LinkedIn rows each), which pushed an otherwise healthy board past its
    timeout and rate limits.
    """
    if base <= 0:
        return 1
    if original_terms <= 0 or consolidated_terms <= 0:
        return min(200, base)
    scaled = (base * original_terms + consolidated_terms - 1) // consolidated_terms
    return min(200, max(base, scaled))


def _source_coverage_entry(
    source: str,
    display_name: str,
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Collapse one source's attempts into the refresh receipt.

    A source that returned useful rows but lost one query is ``partial``, not
    ``failed``. A clean zero is a completed check and remains distinct from a
    source that never answered. The UI uses these states to avoid turning an
    incomplete refresh into a false "nothing new" claim.
    """
    rows_found = sum(max(0, int(item.get("rows_found") or 0)) for item in outcomes)
    failed_attempts = sum(
        1
        for item in outcomes
        if str(item.get("finish_reason") or "zero_rows") in {"timeout", "exception"}
    )
    attempted = len(outcomes)
    errors = [
        str(item.get("error_sample") or "").strip()
        for item in outcomes
        if item.get("error_sample")
    ]

    if attempted == 0:
        state = "failed"
        error = "source produced no outcome"
    elif failed_attempts > 0 and rows_found > 0:
        state = "partial"
        error = errors[0] if errors else f"{failed_attempts} request(s) failed"
    elif failed_attempts > 0:
        state = "failed"
        error = errors[0] if errors else f"{failed_attempts} request(s) failed"
    elif rows_found == 0:
        state = "zero"
        error = ""
    else:
        state = "ok"
        error = ""

    return {
        "source": source,
        "display_name": display_name,
        "state": state,
        "rows_found": rows_found,
        "attempts": attempted,
        "failed_attempts": failed_attempts,
        "error": error[:500],
    }


def _source_coverage_receipt(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize exact per-source outcomes for the API and board toolbar."""
    counts = {state: 0 for state in ("ok", "zero", "partial", "failed")}
    for entry in entries:
        state = str(entry.get("state") or "failed")
        counts[state if state in counts else "failed"] += 1
    return {
        "total": len(entries),
        "ok": counts["ok"],
        "zero": counts["zero"],
        "partial": counts["partial"],
        "failed": counts["failed"],
        "sources": entries,
    }


def _get_specialty_keywords(config: dict | None = None) -> set[str]:
    """Build specialty keyword set from profile config + defaults.

    Includes the profile's technical keywords so domain-specific terms
    (e.g. "Epic", "Cerner" for nurses, "Figma" for designers) are always
    preserved during search consolidation.
    """
    keywords = set(_DEFAULT_SPECIALTY_KEYWORDS)
    if config:
        # Add all short technical keywords from profile
        for kw in config.get("keywords", {}).get("technical", []):
            if len(kw) <= 6:  # short domain terms worth preserving
                keywords.add(kw.lower())
    return keywords


def _strip_prefix(term: str, prefixes: list[str]) -> tuple[str, str]:
    """Strip the first matching prefix from *term*.

    Returns ``(prefix_found, remainder)`` where *remainder* is the stripped
    and whitespace-collapsed base role.  If no prefix matches, *prefix_found*
    is the empty string and *remainder* is the original term (lowered/stripped).
    """
    t = term.lower().strip()
    for pfx in prefixes:
        # Match prefix at start followed by a space (or the whole string)
        if t == pfx:
            return pfx, pfx  # e.g. "CTO" — no strippable prefix
        if t.startswith(pfx + " "):
            remainder = t[len(pfx):].strip()
            if remainder:
                return pfx, remainder
    return "", t


def _consolidate_search_terms(
    roles: list[str],
    keywords: list[str],
    config: dict | None = None,
) -> list[str]:
    """Reduce redundant JobSpy queries by merging similar search terms.

    When a user configures multiple seniority variants of the same role
    (e.g. "senior product manager", "director of product", "VP product"),
    job boards return overlapping results for each variant.  This function
    collapses them into fewer, broader queries to avoid wasting time on
    duplicate searches.

    Works for any profession — engineering, marketing, design, finance, etc.

    Strategy:
    1. Strip seniority/management prefixes ("senior", "director of", etc.)
       to find the *base role*.  Group variants sharing the same base.
    2. Keep one broad query per base instead of many overlapping variants.
    3. Merge near-identical bases (e.g. "product manager" ≈ "product managing").
    4. Always keep short technology/specialty keywords ("SQL", "Figma", etc.).
    5. Keep high-value niche terms ("founding engineer", "first hire", etc.).

    Returns the consolidated list and logs what was merged.
    """
    # --- Phase 1: group roles by base role ---
    # "senior product manager" and "VP product" both have base "product"
    # "senior software engineer" and "staff software engineer" → "software engineer"
    base_groups: dict[str, list[str]] = {}

    for term in roles:
        t = term.strip()
        if not t:
            continue

        pfx, base = _strip_prefix(t, _SENIORITY_PREFIXES)
        if not pfx:
            pfx, base = _strip_prefix(t, _MANAGEMENT_PREFIXES)

        base_key = re.sub(r"\s+", " ", base.lower().strip())
        base_groups.setdefault(base_key, []).append(t)

    # For each group: keep the base role as the search query.
    # When the base is a single generic word (e.g. "marketing" from
    # "VP marketing" + "director of marketing"), use the shortest
    # original term instead — single words return too much noise.
    consolidated: list[str] = []
    kept_bases: set[str] = set()

    for base_key, group in base_groups.items():
        if " " not in base_key and len(group) > 1:
            # Single-word base is too broad — pick shortest original term.
            # e.g. "head of sales" + "VP sales" → search "vp sales" not "sales"
            best = min(group, key=len)
            consolidated.append(best.lower())
            kept_bases.add(base_key)
            logger.info(
                "Consolidated %d terms into '%s' (base '%s' too broad): %s",
                len(group), best, base_key, group,
            )
        else:
            consolidated.append(base_key)
            kept_bases.add(base_key)
            if len(group) > 1:
                logger.info(
                    "Consolidated %d terms into '%s': %s",
                    len(group), base_key, group,
                )

    # --- Phase 1b: merge overlapping multi-word bases ---
    # "product manager" and "product management" return the same job board
    # results.  Merge when one is a word-boundary prefix or suffix variant
    # of another (e.g. -ing, -er, -ment differ by ≤3 chars).
    merged: list[str] = []
    sorted_bases = sorted(consolidated, key=len)
    for term in sorted_bases:
        is_covered = False
        for kept in merged:
            if " " not in kept:
                continue  # single-word terms too broad to absorb others
            # Word prefix: "product manager" covers "product manager operations"
            if term.startswith(kept + " ") or term.startswith(kept + "-"):
                logger.info("'%s' covered by broader query '%s' — skipping", term, kept)
                is_covered = True
                break
            # Suffix variant: "product manager" ≈ "product managing" (≤3 char diff)
            if term.startswith(kept) and len(term) - len(kept) <= 3:
                logger.info("'%s' merged with '%s' (suffix variant) — skipping", term, kept)
                is_covered = True
                break
        if not is_covered:
            merged.append(term)

    consolidated = merged
    # Include original base keys so keyword overlap detection catches
    # terms containing single-word bases (e.g. "sales" in "sales enablement")
    kept_bases = set(merged) | set(base_groups.keys())

    # --- Phase 2: process keyword searches ---
    specialty_kw = _get_specialty_keywords(config)
    for kw in keywords:
        kw_stripped = kw.strip()
        if not kw_stripped:
            continue

        kw_lower = kw_stripped.lower()

        # Always keep short specialty keywords (tools, technologies, etc.)
        if kw_lower in specialty_kw or len(kw_lower) <= 4:
            if kw_stripped not in consolidated:
                consolidated.append(kw_stripped)
            continue

        # Keep high-value niche terms regardless of overlap
        if _HIGH_VALUE_PATTERNS.search(kw_stripped):
            if kw_stripped not in consolidated:
                consolidated.append(kw_stripped)
                logger.info("Keeping high-value keyword: '%s'", kw_stripped)
            continue

        # Skip if this keyword is already covered by an existing role query
        is_covered = any(base in kw_lower for base in kept_bases)
        if is_covered:
            logger.info("Keyword '%s' covered by existing role query — skipping", kw_stripped)
            continue

        if kw_stripped not in consolidated:
            consolidated.append(kw_stripped)
            kept_bases.add(kw_lower)

    logger.info(
        "Search term consolidation: %d roles + %d keywords → %d queries",
        len(roles), len(keywords), len(consolidated),
    )
    return consolidated


def _pick_best_job(group: list[dict]) -> dict:
    """From a group of duplicate jobs, pick the keeper and merge siblings in.

    A direct ATS/company source beats an aggregator copy of the same posting
    (job_trust.DIRECT_SOURCES); among equals the richest record wins (stated
    pay, then description length; see dedup.richness_key).
    """
    best = max(group, key=_dedup_richness_key)

    # Merge useful data from siblings into the best pick
    all_sources = list({j.get("source", "") for j in group if j.get("source")})
    if len(all_sources) > 1:
        best["all_sources"] = all_sources

    # If the best lacks salary data, borrow from a sibling that has it
    if not best.get("salary_min") and not best.get("salary_max"):
        for j in group:
            if j is not best and (j.get("salary_min") or j.get("salary_max")):
                best["salary_min"] = j.get("salary_min")
                best["salary_max"] = j.get("salary_max")
                if j.get("salary_source"):
                    best["salary_source"] = j.get("salary_source")
                break

    # Preserve the newest verifiable cross-source date. A direct ATS often
    # retains the original publication timestamp while an aggregator records
    # a legitimate later repost. Keeping only the direct source's older date
    # made active reposts look expired before ranking.
    from job_finder.tools.scrapers._utils import _parse_posted_date

    dated: list[tuple[datetime, dict]] = []
    for candidate in group:
        if candidate.get("date_confidence") not in ("exact", "fuzzy"):
            continue
        parsed = _parse_posted_date(candidate.get("date_posted"))
        if parsed is None:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        dated.append((parsed, candidate))
    if dated:
        _posted_at, newest = max(dated, key=lambda item: item[0])
        best["date_posted"] = newest.get("date_posted")
        best["date_confidence"] = newest.get("date_confidence")

    # Preserve a discovered official apply URL even when the richer/direct
    # keeper came from a sibling source.
    if not best.get("direct_application_url"):
        for candidate in group:
            if candidate.get("direct_application_url"):
                best["direct_application_url"] = candidate["direct_application_url"]
                break

    return best


def _deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove duplicates while preserving distinct openings.

    When the same job appears from multiple sources (e.g. Indeed, Glassdoor,
    Google Jobs), keeps the version with the richest data and merges salary
    info from siblings. Cross-source merges cluster on the SQUASHED company
    and title keys (dedup.cluster_jobs), so "ALO" on LinkedIn and "Aloyoga"
    on the greenhouse watchlist collide, and only happen when the location is
    compatible and _same_posting confirms (ATS job token, materially identical
    descriptions, or one side too thin to disprove it). A direct ATS/company
    source wins its cluster over aggregator copies.
    """
    from job_finder.tools.scrapers._utils import canonicalize_job_url

    url_groups: dict[str, list[dict]] = {}
    unique: list[dict] = []

    for job in jobs:
        url = job.get("url", "")
        if url:
            # Key on the canonical URL so tracking-param variants (utm_*,
            # ref, gh_src) and Greenhouse/Lever URL shapes of the SAME
            # posting land in one group.
            url_groups.setdefault(canonicalize_job_url(url) or url, []).append(job)
        else:
            unique.append(job)

    collapsed: list[dict] = []
    for group in url_groups.values():
        collapsed.append(_pick_best_job(group) if len(group) > 1 else group[0])
    collapsed.extend(unique)

    # Cross-source pass: cluster on squashed company+title (no location in the
    # key, so cross-board duplicates that differ in location text, or have no
    # location on one source, still land in the same group; _same_posting then
    # separates distinct openings).
    clusters, no_key = _cluster_jobs(collapsed)

    unique = []
    for cluster in clusters:
        if len(cluster) == 1:
            unique.append(cluster[0])
            continue
        best = _pick_best_job(cluster)
        losers = [j for j in cluster if j is not best]
        logger.info(_describe_collapse(best, losers))
        unique.append(best)

    unique.extend(no_key)
    return unique


def _resolve_location_filter_preferences(
    locations: list[str],
    loc_prefs: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]], bool, bool, list[str]]:
    """Resolve post-search location filtering from explicit prefs or raw locations.

    The 7th element is ``preferred_countries`` — derived from the preferred
    locations so a US-based search scopes remote jobs to the US ("if cities are
    in the US, remote has to be in the US"). Empty when no country signal is
    present (e.g. a Remote-only search), so ambiguous remote is never dropped.
    """
    loc_prefs = loc_prefs or {}
    from job_finder.company_classifier import parse_location as _parse_loc

    def _derive_countries(values: list[str]) -> list[str]:
        countries: list[str] = []
        for value in values:
            parsed = _parse_loc(value)
            if parsed.get("country") == "non-us":
                name = parsed.get("country_name") or "non-us"
            elif parsed.get("country") == "US" or parsed.get("state"):
                name = "united states"
            else:
                continue
            if name not in countries:
                countries.append(name)
        return countries

    def _derive_state_city_lists(values: list[str]) -> tuple[list[str], list[str]]:
        states: list[str] = []
        cities: list[str] = []
        for value in values:
            parsed = _parse_loc(value)
            if parsed["state"] and parsed["state"] not in states:
                states.append(parsed["state"])
            if parsed["city"] and parsed["city"] not in cities:
                cities.append(parsed["city"])
        return states, cities

    def _derive_place_payloads(values: list[str]) -> list[dict[str, Any]]:
        places: list[dict[str, Any]] = []
        for value in values:
            parsed = _parse_loc(value)
            scope = "city"
            if parsed.get("country") == "non-us" and not parsed.get("city"):
                scope = "country"
            elif parsed.get("state") and not parsed.get("city"):
                scope = "region"
            elif parsed.get("country_name") and not parsed.get("city") and not parsed.get("state"):
                scope = "country"
            places.append({
                "label": value,
                "kind": "manual",
                "match_scope": scope,
                "city": parsed.get("city", ""),
                "region": parsed.get("state", ""),
                "country": parsed.get("country_name", ""),
                "country_code": parsed.get("country", ""),
            })
        return places

    if loc_prefs.get("filter_enabled", False):
        preferred_locations = list(loc_prefs.get("preferred_locations", []))
        preferred_states = list(loc_prefs.get("preferred_states", []))
        preferred_cities = list(loc_prefs.get("preferred_cities", []))
        preferred_places = list(loc_prefs.get("preferred_places", []))
        if preferred_locations and not (preferred_states or preferred_cities):
            derived_states, derived_cities = _derive_state_city_lists(preferred_locations)
            preferred_states = derived_states
            preferred_cities = derived_cities
        if preferred_locations and not preferred_places:
            preferred_places = _derive_place_payloads(preferred_locations)
        preferred_countries = (
            list(loc_prefs.get("preferred_countries", []))
            or _derive_countries(preferred_locations)
        )
        return (
            preferred_locations,
            preferred_states,
            preferred_cities,
            preferred_places,
            bool(loc_prefs.get("remote_only", False)),
            bool(loc_prefs.get("include_remote", True)),
            preferred_countries,
        )

    pref_locations = [
        loc for loc in locations
        if loc.lower() not in ("remote", "united states", "usa", "us", "anywhere")
    ]
    pref_states: list[str] = []
    pref_cities: list[str] = []
    remote_only = bool(loc_prefs.get("remote_only", False))
    if "include_remote" in loc_prefs:
        include_remote = bool(loc_prefs.get("include_remote", True))
    else:
        include_remote = not locations or any(
            loc.lower() in ("remote", "united states", "usa", "us", "anywhere")
            for loc in locations
        )

    derived_states, derived_cities = _derive_state_city_lists(pref_locations)
    pref_states.extend([state for state in derived_states if state not in pref_states])
    pref_cities.extend([city for city in derived_cities if city not in pref_cities])

    return (
        pref_locations,
        pref_states,
        pref_cities,
        _derive_place_payloads(pref_locations),
        remote_only,
        include_remote,
        _derive_countries(pref_locations),
    )


def _filter_jobs_by_freshness(
    jobs: list[dict],
    max_days_old: int,
    *,
    now: datetime | None = None,
    drop_missing_dates: bool = False,
) -> list[dict]:
    """Drop postings older than ``max_days_old`` by their real post date.

    max_days_old is otherwise only an upstream hint most boards ignore, so a
    months-old reposting can slip through. By default, jobs whose date is
    missing or unparseable are KEPT (we don't drop on uncertainty); under the
    strict preset ``drop_missing_dates=True`` drops jobs whose
    ``date_confidence`` is 'missing' — no verifiable date means the posting
    can't be proven fresh. A 1-day skew buffer absorbs timezone/repost
    differences. ``max_days_old <= 0`` disables it.
    """
    if not max_days_old or max_days_old <= 0:
        return jobs
    from job_finder.tools.scrapers._utils import _parse_posted_date

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_days_old + 1)
    kept: list[dict] = []
    for job in jobs:
        dt = _parse_posted_date(job.get("date_posted"))
        if dt is None:
            # Unstamped jobs with an unparseable date are 'missing' too.
            confidence = job.get("date_confidence") or "missing"
            if drop_missing_dates and confidence == "missing":
                continue
            kept.append(job)  # unknown date → keep (default presets)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt >= cutoff:
            kept.append(job)
    return kept


def _resolve_salary_floor(config: dict | None) -> float:
    """Annualized salary floor (before strictness flex) from the user's config.

    Reads ``min_acceptable_tc`` / ``min_base`` from BOTH ``compensation`` and
    ``career_baseline``: the Settings UI persists the hard floor under
    ``career_baseline`` while older config/templates use ``compensation``, so
    the filter must honor either — otherwise the UI control silently does
    nothing (the dead-key bug). Returns 0 when no floor is configured.
    """
    config = config or {}
    comp_cfg = config.get("compensation", {}) or {}
    career_cfg = config.get("career_baseline", {}) or {}
    pay_period = comp_cfg.get("pay_period", "annual")
    raw = (
        comp_cfg.get("min_acceptable_tc")
        or career_cfg.get("min_acceptable_tc")
        or comp_cfg.get("min_base")
        or career_cfg.get("min_base")
        or 0
    )
    return annualize_amount(raw, pay_period) or 0


def _annualize_raw_salary(value: float | None, period: str | None) -> float | None:
    """Best-effort annualization when the salary_*_annualized fields are absent.

    Uses the stamped ``salary_period`` when present. Without a period, a value
    under 1000 cannot be an annual figure (no job pays $500/yr) — it's an
    hourly rate that would otherwise be compared raw against an annual floor
    and wrongly dropped, so treat it as hourly (x2080).
    """
    if value is None:
        return None
    period_key = (period or "").strip().lower()
    if period_key:
        annualized = annualize_amount(value, period_key)
        if annualized is not None:
            return annualized
    if 0 < value < 1000:
        return value * 2080.0
    return value


def watchlist_tokens_by_ats(raw_watchlist: list, resolve) -> dict[str, list[str]]:
    """Group watchlist board tokens by ATS, trusting stored tokens first.

    Entries carrying a confirmed ats/slug keep them verbatim; a company the
    catalog does not know (BILL -> billcom) must never lose its token to a
    failed re-resolution. Bare names and unknown entries go through
    ``resolve`` (the company catalog). Tokens dedupe per ATS.
    """
    by_ats: dict[str, list[str]] = {}

    def _add(ats: str, slug: str) -> None:
        if ats and slug and ats != "unknown" and slug not in by_ats.setdefault(ats, []):
            by_ats[ats].append(slug)

    unresolved: list[str] = []
    for entry in raw_watchlist:
        if isinstance(entry, dict) and entry.get("slug") and entry.get("ats", "unknown") != "unknown":
            _add(entry["ats"], entry["slug"])
        else:
            name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
            if name:
                unresolved.append(name)
    if unresolved:
        for entry in resolve(unresolved):
            _add(entry.get("ats", ""), entry.get("slug", ""))
    return {ats: slugs for ats, slugs in by_ats.items() if slugs}


def _job_salary_passes(
    job: dict,
    hard_floor: float,
    target_currency: str | None = None,
) -> bool:
    """Return True if the job's salary meets the hard floor, or is unknown.

    Uses the midpoint of the salary range when both min and max are known,
    otherwise uses salary_max. Jobs with no salary data always pass —
    filtering them out would remove most listings. Raw values are annualized
    first (via salary_period, or the obviously-hourly heuristic) so an
    hourly role is never compared raw against the annual floor. When a user's
    target currency is known, a missing or different listing currency is also
    kept: unlike-currency numbers are not comparable without an explicit FX
    policy, and silently treating them as dollars would make the filter lie.
    """
    # Some aggregators publish modeled salary bands explicitly labeled as
    # estimates. They are useful context on the card, but not strong enough to
    # exclude an otherwise relevant job from a user's hard compensation floor.
    if str(job.get("salary_source") or "").strip().lower() == "source_estimate":
        return True

    if target_currency:
        listing_currency = str(job.get("salary_currency") or "").strip().upper()
        if not listing_currency or listing_currency != target_currency.strip().upper():
            return True

    # Use explicit None checks — 0 is a valid (if incorrect) salary value
    # and must not be treated as "no data"
    period = job.get("salary_period")
    _sal_max = job.get("salary_max_annualized")
    if _sal_max is None:
        _sal_max = _annualize_raw_salary(job.get("salary_max"), period)
    _sal_min = job.get("salary_min_annualized")
    if _sal_min is None:
        _sal_min = _annualize_raw_salary(job.get("salary_min"), period)

    # No salary data → let it through
    if _sal_max is None and _sal_min is None:
        return True

    # Both min and max → use midpoint
    if _sal_min is not None and _sal_max is not None:
        midpoint = (_sal_min + _sal_max) / 2
        return midpoint >= hard_floor

    # Only max known → check max directly
    if _sal_max is not None:
        return _sal_max >= hard_floor

    # Only min known → check min directly
    return _sal_min >= hard_floor


# Filter-strictness presets. Each preset is a complete default; user-supplied
# keys in config["filters"] override individual values via _resolve_filter_settings().
# Loose = wide net (new default), Balanced = the previous hardcoded behavior,
# Strict = tight matches only. Surfaced via the SearchRequest.match_strictness
# field and the Match strictness segmented control in the UI.
_FILTER_PRESETS: dict[str, dict[str, Any]] = {
    "loose": {
        "salary_flex": 0.70,
        "level_tolerance_senior": 2.5,
        "level_tolerance_junior": 3.0,
        "include_founding_titles": True,
        "role_match_mode": "any_word",
        "drop_missing_dates": False,
    },
    "balanced": {
        "salary_flex": 0.85,
        "level_tolerance_senior": 1.5,
        "level_tolerance_junior": 2.0,
        "include_founding_titles": True,
        "role_match_mode": "all_significant",
        "drop_missing_dates": False,
    },
    "strict": {
        "salary_flex": 1.00,
        "level_tolerance_senior": 1.0,
        "level_tolerance_junior": 1.0,
        "include_founding_titles": False,
        "role_match_mode": "exact",
        # No verifiable posting date → can't prove freshness → drop.
        "drop_missing_dates": True,
    },
}

_DEFAULT_STRICTNESS = "balanced"


def _source_category(source: str | None) -> str | None:
    """Scraper category ("startup"|"ats"|"crypto"|...) for a job's source.

    Used so an otherwise-Unknown company from a startup-leaning board can be
    tagged as a startup tier (see ``classify_company``). Returns None for
    JobSpy/remote/general sources that aren't startup-specific.
    """
    if not source:
        return None
    try:
        from job_finder.tools.scrapers._registry import get_registry
        meta = get_registry().get(source)
        return meta.category if meta else None
    except Exception:
        return None


def _resolve_filter_settings(config: dict | None) -> dict[str, Any]:
    """Materialize the active filter settings.

    Reads ``config["filters"]``. The optional ``strictness`` key picks a preset
    (``loose|balanced|strict``); any other keys override the preset values
    one-by-one. Unknown strictness values fall back to the default preset so a
    typo in YAML never silently disables filtering.
    """
    raw = (config or {}).get("filters") or {}
    strictness = str(raw.get("strictness") or _DEFAULT_STRICTNESS).strip().lower()
    preset = _FILTER_PRESETS.get(strictness) or _FILTER_PRESETS[_DEFAULT_STRICTNESS]
    resolved = dict(preset)
    for key in (
        "salary_flex",
        "level_tolerance_senior",
        "level_tolerance_junior",
        "include_founding_titles",
        "role_match_mode",
        "drop_missing_dates",
    ):
        if key in raw:
            resolved[key] = raw[key]
    resolved["strictness"] = strictness if strictness in _FILTER_PRESETS else _DEFAULT_STRICTNESS
    return resolved


def _filter_jobs_by_level(
    jobs: list[dict],
    career_cfg: dict | None,
    *,
    filters: dict | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Filter jobs that are too far above or below the configured level."""
    career_cfg = career_cfg or {}
    current_title = str(career_cfg.get("current_title", "") or "").strip()
    current_level_label = str(career_cfg.get("current_level", "") or "").strip()
    if not current_title and not current_level_label:
        return jobs

    resolved = filters or _resolve_filter_settings(None)
    tol_senior = float(resolved.get("level_tolerance_senior", 1.5))
    tol_junior = float(resolved.get("level_tolerance_junior", 2.0))

    current_level = resolve_current_level(career_cfg)
    pre_count = len(jobs)
    if current_level >= 3:
        filtered = [
            job for job in jobs
            if _extract_level(job.get("title", "")) >= current_level - tol_senior
        ]
    else:
        filtered = [
            job for job in jobs
            if _extract_level(job.get("title", "")) <= current_level + tol_junior
        ]

    dropped = pre_count - len(filtered)
    if dropped and progress:
        level_label = current_title or current_level_label
        progress(f"Level filter: removed {dropped} jobs outside {level_label} level range")
    return filtered


def _backfill_linkedin_descriptions(
    jobs: list[dict],
    max_workers: int = 8,
    max_retries: int = 2,
    retry_delay: float = 1.0,
) -> None:
    """Fetch descriptions for LinkedIn-only jobs that lack them.

    Called after dedup for the small subset of jobs that only appeared on
    LinkedIn and therefore have no description (because we skipped
    ``linkedin_fetch_description`` during the fast search pass).

    Modifies *jobs* in place.  Uses a simple requests GET + HTML parse.
    Retries up to *max_retries* times on transient failures (non-200
    status codes, network errors) with *retry_delay* seconds between
    attempts.
    """
    import requests
    from bs4 import BeautifulSoup

    def _fetch_one(job: dict) -> None:
        url = job.get("url", "")
        if not url:
            return
        for attempt in range(1 + max_retries):
            try:
                resp = requests.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    },
                    timeout=10,
                    allow_redirects=True,
                )
                if resp.status_code != 200:
                    if attempt < max_retries:
                        logger.debug(
                            "LinkedIn backfill got %d for %s, retrying (%d/%d)",
                            resp.status_code, url, attempt + 1, max_retries,
                        )
                        time.sleep(retry_delay)
                        continue
                    logger.debug(
                        "LinkedIn backfill gave up on %s after %d retries (status %d)",
                        url, max_retries, resp.status_code,
                    )
                    return
                soup = BeautifulSoup(resp.text, "html.parser")
                # LinkedIn job pages embed description in a specific div
                desc_el = (
                    soup.select_one(".description__text")
                    or soup.select_one(".show-more-less-html__markup")
                    or soup.select_one("[class*='description']")
                )
                if desc_el:
                    # Parse the whole body, store an excerpt. LinkedIn puts the
                    # hiring range last, so truncating first hides the pay from
                    # the salary extraction that runs right after this.
                    full = desc_el.get_text(separator="\n", strip=True)
                    job["description"] = full[:3000]
                    job["description_full"] = full
                return  # success — no retry needed
            except Exception as e:
                if attempt < max_retries:
                    logger.debug(
                        "LinkedIn backfill failed for %s: %s, retrying (%d/%d)",
                        url, e, attempt + 1, max_retries,
                    )
                    time.sleep(retry_delay)
                else:
                    logger.debug(
                        "LinkedIn backfill gave up on %s after %d retries: %s",
                        url, max_retries, e,
                    )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(_fetch_one, jobs))


def _career_scraper_enabled(meta, yaml_entry: dict | None) -> bool:
    """Whether the career pipeline may enable this scraper.

    Non-career scrapers are never enabled here, not even when the user's yaml
    says enabled: true. Quest ingestion has its own entry point, so a quest
    source toggled on in settings can never route audience seats or study
    listings into resume scoring and career purges.
    """
    if meta.search_fn is None:
        return False
    if getattr(meta, "vertical", "career") != "career":
        return False
    if yaml_entry is not None:
        return bool(yaml_entry.get("enabled", True))
    return meta.enabled_by_default


class JobFinderPipeline:
    """Orchestrates the full job-search pipeline.

    Parameters
    ----------
    llm : LLMClient or None
        When *None*, AI features (smart scoring, cover letters, resume tweaks,
        company research) are disabled.  Search + basic scoring still work.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        profile: str | None = None,
    ) -> None:
        self.llm = llm
        self.profile_name = profile or "default"
        self.config = _load_search_config(profile)
        self._preloaded_resume_text: str | None = None
        self._last_funnel: list[dict] = []

    def _record_funnel_stage(
        self,
        key: str,
        label: str,
        count_in: int,
        count_out: int,
        *,
        active: bool = True,
    ) -> None:
        """Append a stage entry to the per-search funnel.

        ``active=False`` records that the stage was skipped (no preference
        configured) so the UI can grey it out instead of hiding it.
        """
        dropped = max(count_in - count_out, 0)
        self._last_funnel.append({
            "key": key,
            "label": label,
            "count_in": count_in,
            "count_out": count_out,
            "dropped": dropped,
            "active": active,
        })

    # -- Stage 0.5: AI role expansion (optional) ----------------------------

    def expand_roles_with_ai(
        self,
        roles: list[str],
        progress: Callable[[str], None] | None = None,
    ) -> list[str]:
        """Use LLM to expand target roles into related job title keywords.

        Given roles like ["nurse practitioner", "clinical director"], the LLM
        returns additional relevant title keywords (e.g. "APRN", "primary care
        provider", "FNP-C") that scrapers should match against.

        Returns the original roles + AI-generated expansions.  Falls back to
        just the original roles if the LLM is unavailable or fails.

        Results are cached to disk per profile + role-set hash so we don't
        re-pay the LLM call every search run. Cache file:
        ``<data_dir>/expanded_roles_<profile>_<hash>.json``.
        """
        if not self.llm or not self.llm.is_configured:
            return roles
        if not roles:
            return roles

        # Try persistent cache before hitting the LLM. Roles + profile hash
        # invalidates naturally when the user edits target_roles or switches
        # profile. Cache is only used when LLM is configured — keeps the
        # no-LLM offline path identical to before.
        import hashlib
        cache_key = hashlib.sha1(
            ("|".join(sorted(r.lower().strip() for r in roles))).encode("utf-8")
        ).hexdigest()[:10]
        profile_slug = (self.profile_name or "default").replace("/", "_")
        data_dir = os.getenv("JOB_FINDER_DATA_DIR", os.path.join(os.getcwd(), "data"))
        cache_path = os.path.join(data_dir, f"expanded_roles_{profile_slug}_{cache_key}.json")
        try:
            if os.path.exists(cache_path):
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, list) and cached:
                    if progress:
                        progress(f"Using cached role expansion ({len(cached)} keywords)")
                    return cached
        except Exception as e:
            logger.debug("Role expansion cache read failed (non-fatal): %s", e)

        roles_str = ", ".join(f'"{r}"' for r in roles)
        system_prompt = (
            "You are a job search expert. Given a list of target job titles/roles, "
            "generate additional related job title keywords that a candidate with "
            "these roles would be qualified for and interested in.\n\n"
            "Rules:\n"
            "- ONLY return titles/keywords within the SAME profession and industry\n"
            "- Do NOT cross industries (e.g. nursing roles should NOT include software engineering)\n"
            "- Include common abbreviations, alternate titles, and related specializations\n"
            "- Keep each keyword short (1-4 words)\n"
            "- Return 10-20 additional keywords\n"
            "- Reply with valid JSON: {\"expanded_keywords\": [\"keyword1\", \"keyword2\", ...]}"
        )
        user_msg = f"Target roles: {roles_str}"

        try:
            result = self.llm.chat_json(system_prompt, user_msg, temperature=0.2)
            if result and "expanded_keywords" in result:
                expanded = result["expanded_keywords"]
                if isinstance(expanded, list) and expanded:
                    # Merge with originals, dedup
                    all_keywords = list(roles)
                    seen = {r.lower() for r in roles}
                    for kw in expanded:
                        if isinstance(kw, str) and kw.strip():
                            kw_lower = kw.strip().lower()
                            if kw_lower not in seen:
                                all_keywords.append(kw.strip())
                                seen.add(kw_lower)
                    logger.info(
                        "AI role expansion: %d roles → %d keywords (+%d)",
                        len(roles), len(all_keywords), len(all_keywords) - len(roles),
                    )
                    if progress:
                        progress(
                            f"AI expanded {len(roles)} roles → {len(all_keywords)} "
                            f"keywords (+{len(all_keywords) - len(roles)} related titles)"
                        )
                    # Persist to disk so future runs reuse instead of paying again.
                    try:
                        os.makedirs(data_dir, exist_ok=True)
                        with open(cache_path, "w", encoding="utf-8") as f:
                            json.dump(all_keywords, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        logger.debug("Role expansion cache write failed (non-fatal): %s", e)
                    return all_keywords
        except Exception as e:
            logger.warning("AI role expansion failed (non-fatal): %s", e)

        return roles

    # -- Stage 1: Search (no LLM) -----------------------------------------

    def search_all_jobs(
        self,
        roles: list[str] | None = None,
        locations: list[str] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Scrape job boards for every role x location combination **in parallel**.

        JobSpy searches and additional scrapers run concurrently.
        Returns a deduplicated list of job dicts.
        """
        # A missing legacy config still needs a country-scale search location,
        # but it must never inherit the maintainer's city. Normal workspace
        # searches supply the person's own selected places before this point.
        locations = locations or self.config.get("locations") or ["United States"]
        settings = self.config.get("search_settings") or {}
        results_per_board = max(1, settings.get("results_per_board", 50))
        # Per-source cap. The ATS scrapers scan hundreds of company boards; the
        # cap now truncates the RELEVANCE-RANKED results (see rank_by_relevance),
        # so the strongest role matches survive. It's set high because a
        # location-specific role (e.g. ALO in LA) can sit behind hundreds of
        # equally-relevant remote roles that the location filter later drops, and
        # the cap runs before that filter. The scraper already fetched every
        # board, so a higher cap costs almost nothing (it only keeps more rows).
        # Floor at 500 regardless of the loaded profile: a lower per-source cap
        # silently drops relevant company jobs (e.g. ALO's Manager of Data
        # Engineering sat behind 100 exact matches), which we never want.
        results_per_additional = max(500, int(settings.get("results_per_additional_source", 500) or 500))
        max_days_old = max(1, settings.get("max_days_old", 30))
        search_distance = settings.get("search_radius_miles")  # None = JobSpy default (50 miles)
        configured_jobspy_boards = self.config.get("job_boards")
        # Missing means legacy/default boards; an explicit [] is a real opt-out.
        # Collapsing both through ``or None`` silently re-enabled blocked or
        # deliberately disabled sources during targeted refreshes.
        jobspy_boards = (
            configured_jobspy_boards
            if isinstance(configured_jobspy_boards, list)
            else None
        )

        # Build the consolidated query list: target_roles + title-shaped
        # keyword_searches + title-shaped resume skills (keywords.technical).
        # When roles are passed explicitly (e.g. from the API, which already
        # merges keywords into the roles list), keyword_searches is not
        # re-read — that would double-count it.
        consolidated, roles_raw, keywords_raw = _build_search_terms(self.config, roles)

        # Broader queries → more results per query to compensate
        original_count = len(roles_raw) + len(keywords_raw)
        if consolidated and len(consolidated) < original_count:
            results_per_board = _scaled_results_per_board(
                results_per_board,
                original_count,
                len(consolidated),
            )
            logger.info(
                "Consolidated %d → %d search terms; bumped results_per_board to %d",
                original_count, len(consolidated), results_per_board,
            )

        if not consolidated:
            logger.warning(
                "No search terms generated from roles=%s keywords=%s",
                roles_raw, keywords_raw,
            )
            if progress:
                progress("Warning: no search terms found — check target_roles and keyword_searches in config")

        # Build search tasks, ordered so niche/specific queries run first.
        # This ensures high-value targeted searches (technology keywords,
        # founding roles) always execute before early stopping kicks in.
        # Broad base-role queries that return mostly duplicates run last.
        # Run real job TITLES first so the user's core role searches aren't
        # starved when a board's circuit breaker trips (rate limit) mid-run.
        specialty_kw = _get_specialty_keywords(self.config)
        prioritized = sorted(consolidated, key=lambda t: _search_query_priority(t, specialty_kw))
        search_tasks: list[tuple[str, str]] = []
        # Cover every role in the primary place before spending a second query
        # on the same role elsewhere. The old role-major order could use the
        # entire task budget on the first few titles (city + remote) and never
        # ask a board about later saved roles at all.
        for loc in locations:
            for term in prioritized:
                search_tasks.append((term, loc))

        # Hard cap on total search tasks to avoid 8+ minute searches.
        # High-priority (niche) queries are at the front, so trimming
        # from the back drops only broad/duplicate-heavy queries.
        max_tasks = max(12, settings.get("max_search_tasks", 30))
        if len(search_tasks) > max_tasks:
            trimmed = len(search_tasks) - max_tasks
            search_tasks = search_tasks[:max_tasks]
            logger.info(
                "Capped search tasks from %d to %d (dropped %d low-priority queries)",
                max_tasks + trimmed, max_tasks, trimmed,
            )
            if progress:
                progress(f"Capped to {max_tasks} search queries (dropped {trimmed} low-priority duplicates)")

        total_combos = len(search_tasks)
        jobspy_tasks = _build_jobspy_tasks(search_tasks, jobspy_boards)
        total_tasks = len(jobspy_tasks)
        counter = {"done": 0}
        lock = threading.Lock()
        all_jobs: list[dict] = []
        # Early stopping is isolated PER BOARD. A prolific Indeed query must
        # never cancel LinkedIn (or any other board) before it has answered.
        # Each board also gets at least one planned query per consolidated role
        # before its own volume cap may stop secondary-location work.
        max_unique = max(100, settings.get("max_unique_jobs", 500))
        minimum_queries_per_board = min(
            total_combos,
            max(
                1,
                int(settings.get("min_queries_per_source", len(prioritized)) or len(prioritized)),
            ),
        ) if total_combos else 0
        board_seen_urls: dict[str, set[str]] = {}
        board_unique_counts: dict[str, int] = {}
        board_done_counts: dict[str, int] = {}
        board_stop_events: dict[str, threading.Event] = {}
        jobspy_outcomes: dict[str, list[dict[str, Any]]] = {}
        jobspy_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        jobspy_started_mono = time.monotonic()

        # Per-board scrape deadline (seconds). Generous enough for a healthy
        # board returning a full page, tight enough that a hung/CAPTCHA board
        # can't stall the search for minutes. Configurable via search_settings.
        jobspy_task_timeout = float(settings.get("jobspy_task_timeout_seconds", 45) or 45)

        def _search_one(task: tuple[str, str, list[str] | None]) -> list[dict]:
            term, loc, task_boards = task
            board_key = task_boards[0].strip().lower() if task_boards else "jobspy"
            with lock:
                stop_event = board_stop_events.setdefault(board_key, threading.Event())
            # Skip only this board after it has satisfied its own coverage and
            # volume budget; other boards continue independently.
            if stop_event.is_set():
                return []
            telemetry: dict[str, Any] = {
                "term": term,
                "location": loc,
            }
            jobs: list[dict] = []
            try:
                is_remote = True if loc.lower() == "remote" else None
                country_by_location = settings.get("country_by_location", {}) or {}
                task_country = str(
                    country_by_location.get(loc.casefold())
                    or settings.get("country")
                    or "USA"
                )
                telemetry["country"] = task_country
                jobs = search_jobs(
                    search_term=term,
                    location=loc if loc.lower() != "remote" else task_country,
                    results_wanted=results_per_board,
                    hours_old=max_days_old * 24,
                    is_remote=is_remote,
                    country=task_country,
                    boards=task_boards,
                    # Skip fetching full LinkedIn page per result (~2-3s each).
                    # Descriptions still come from Indeed, Glassdoor, Google.
                    # LinkedIn results keep title/company/location/salary/URL.
                    linkedin_fetch_description=False,
                    distance=search_distance,
                    # Cap each board scrape so one hung/CAPTCHA-walled board can't
                    # stall a worker for minutes. After a few timeouts the per-board
                    # circuit breaker opens and the board is skipped outright.
                    scrape_timeout=jobspy_task_timeout,
                    telemetry=telemetry,
                )
                # Protect the receipt contract even if a replacement wrapper
                # forgets to fill telemetry.
                telemetry.setdefault("finish_reason", "ok" if jobs else "zero_rows")
                telemetry.setdefault("rows_found", len(jobs))
                telemetry.setdefault("error_sample", "")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                telemetry.update({
                    "finish_reason": "exception",
                    "rows_found": 0,
                    "error_sample": error[:500],
                })
                logger.warning(
                    "JobSpy %s search failed for %r in %r (non-fatal): %s",
                    board_key,
                    term,
                    loc,
                    error,
                    exc_info=True,
                )
            with lock:
                jobspy_outcomes.setdefault(board_key, []).append(telemetry)
                counter["done"] += 1
                n = counter["done"]
                board_done_counts[board_key] = board_done_counts.get(board_key, 0) + 1
                seen_urls = board_seen_urls.setdefault(board_key, set())
                new_count = 0
                for j in jobs:
                    url = j.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        new_count += 1
                board_unique_counts[board_key] = board_unique_counts.get(board_key, 0) + new_count
                if (
                    board_unique_counts[board_key] >= max_unique
                    and board_done_counts[board_key] >= minimum_queries_per_board
                ):
                    stop_event.set()
            if progress:
                sources = ", ".join(set(j.get("source", "?") for j in jobs)) if jobs else "no boards"
                suffix = f" ({board_key} coverage complete)" if stop_event.is_set() else ""
                progress(f"  [{n}/{total_tasks}] '{term}' in {loc} → {len(jobs)} results from {sources}{suffix}")
            return jobs

        # --- Launch JobSpy searches + additional scrapers concurrently ---
        if progress:
            if isinstance(jobspy_boards, list) and jobspy_boards:
                progress(
                    f"Searching {total_combos} role×location combos across "
                    f"{len(jobspy_boards)} boards ({total_tasks} source searches) in parallel..."
                )
            else:
                progress(f"Searching {total_combos} role×location combos in parallel...")

        # ``max_parallel_searches`` remains the concurrency budget PER board.
        # Splitting explicit boards creates one outer task per board, so scale
        # the pool by the number of boards. This preserves the old number of
        # network requests (six role/location calls × N internal JobSpy board
        # workers) without letting a slow board hold a healthy board's rows.
        board_count = len(jobspy_boards) if isinstance(jobspy_boards, list) else 1
        max_jobspy_workers = min(
            total_tasks,
            max(1, int(settings.get("max_parallel_searches", 6))) * max(1, board_count),
        )

        # Prepare additional scraper arguments
        enabled_names: list[str] = []
        all_scrapers: dict[str, Any] = {}
        try:
            from job_finder.tools.scrapers import get_registry, run_scrapers

            extra_sources = self.config.get("additional_sources", [])
            all_scrapers = get_registry()

            # Warn about typos in config scraper names
            config_names = {s.get("name") for s in extra_sources if s.get("name")}
            unknown = config_names - set(all_scrapers.keys())
            if unknown:
                logger.warning("Config lists unknown scrapers (typo?): %s", unknown)

            for name, meta in all_scrapers.items():
                yaml_entry = next(
                    (s for s in extra_sources if s.get("name") == name), None
                )
                if _career_scraper_enabled(meta, yaml_entry):
                    enabled_names.append(name)

            # Build watchlist_by_ats from profile config + company catalog.
            # Entries that carry a confirmed ats/slug (discovery or a pasted
            # careers link stored them) are trusted as-is; only bare names
            # and unknowns go through the catalog.
            from job_finder.config.company_catalog import resolve_watchlist
            raw_watchlist = self.config.get("watchlist", [])
            watchlist_by_ats = watchlist_tokens_by_ats(raw_watchlist, resolve=resolve_watchlist)
            # Enable ATS scrapers that have watchlist companies (career only)
            for ats_name in watchlist_by_ats:
                if (
                    ats_name not in enabled_names
                    and ats_name in all_scrapers
                    and getattr(all_scrapers[ats_name], "vertical", "career") == "career"
                ):
                    enabled_names.append(ats_name)
        except Exception as e:
            logger.warning("Could not load scraper registry: %s", e)
            watchlist_by_ats = {}

        # Use AI to expand role keywords for source recall only. Hosted
        # managed-AI disables this per-search call; confirmed roles remain the
        # only route into the primary result bucket either way.
        # This helps non-tech profiles (nurse, marketer, etc.) by generating
        # related title keywords the LLM knows about, so scrapers can filter
        # more intelligently beyond just substring matching.
        if (self.config.get("search_settings") or {}).get("ai_expand_roles", True):
            scraper_roles = self.expand_roles_with_ai(roles_raw, progress=progress)
        else:
            scraper_roles = list(roles_raw)
        # Store expanded roles so filter_by_role uses them too
        self._expanded_roles = scraper_roles

        # Run JobSpy searches in a thread pool, and additional scrapers
        # concurrently in their own thread.
        extra_jobs_result: list[dict] = []
        additional_outcomes: list[dict[str, Any]] = []

        # Resolve filter strictness once and pass it into scrapers so their
        # per-job _match_roles calls use the same mode/founding-bypass as
        # the pipeline-level filter. Otherwise scrapers silently default to
        # "all_significant" and reject legitimate matches the user's loose
        # preset would otherwise pass.
        scraper_filter_settings = _resolve_filter_settings(self.config)

        def _run_additional_scrapers() -> None:
            nonlocal extra_jobs_result
            try:
                from job_finder.tools.scrapers import run_scrapers
                extra_jobs_result = run_scrapers(
                    names=enabled_names,
                    roles=scraper_roles,
                    max_results=results_per_additional,
                    progress=progress,
                    locations=locations,
                    max_days_old=max_days_old,
                    watchlist_by_ats=watchlist_by_ats,
                    filters=scraper_filter_settings,
                    outcome_sink=additional_outcomes,
                )
            except Exception as e:
                logger.warning("Additional scrapers failed (non-fatal): %s", e)
                if progress:
                    progress(f"  Additional scrapers error: {e}")

        # Start additional scrapers in background thread
        scraper_thread = None
        if enabled_names:
            scraper_thread = threading.Thread(
                target=_run_additional_scrapers, daemon=True
            )
            scraper_thread.start()

        # Run JobSpy searches in parallel
        if jobspy_tasks:
            with ThreadPoolExecutor(max_workers=max_jobspy_workers) as pool:
                futures = {pool.submit(_search_one, t): t for t in jobspy_tasks}
                cancelled_boards: set[str] = set()
                for future in as_completed(futures):
                    try:
                        all_jobs.extend(future.result())
                    except Exception as e:
                        logger.warning("JobSpy search failed (non-fatal): %s", e)
                    # Cancel queued work only for boards that independently met
                    # their cap. Already-running calls still return their rows.
                    for board_key, stop_event in list(board_stop_events.items()):
                        if not stop_event.is_set() or board_key in cancelled_boards:
                            continue
                        cancelled_boards.add(board_key)
                        cancelled = 0
                        for queued, queued_task in futures.items():
                            queued_boards = queued_task[2]
                            queued_key = queued_boards[0].strip().lower() if queued_boards else "jobspy"
                            if queued_key == board_key and queued.cancel():
                                cancelled += 1
                        if cancelled:
                            logger.info(
                                "Early stop: cancelled %d queued %s searches after minimum coverage",
                                cancelled,
                                board_key,
                            )

        # JobSpy boards used to be invisible to source health because only
        # plugin scrapers wrote scrape_runs. Persist one aggregate outcome per
        # board per pull so LinkedIn/Indeed freshness and failures are auditable
        # exactly like ATS, startup, crypto, remote, and community sources.
        if jobspy_outcomes:
            try:
                from job_finder.models.database import record_scrape_runs

                elapsed = max(0.0, time.monotonic() - jobspy_started_mono)
                logged: list[dict[str, Any]] = []
                for board_key, outcomes in jobspy_outcomes.items():
                    reasons = [str(item.get("finish_reason") or "zero_rows") for item in outcomes]
                    rows_found = sum(int(item.get("rows_found") or 0) for item in outcomes)
                    failures = reasons.count("timeout") + reasons.count("exception")
                    if failures and rows_found > 0:
                        finish_reason = "partial"
                    elif "timeout" in reasons:
                        finish_reason = "timeout"
                    elif "exception" in reasons:
                        finish_reason = "exception"
                    elif rows_found == 0:
                        finish_reason = "zero_rows"
                    else:
                        finish_reason = "ok"
                    errors = [
                        str(item.get("error_sample") or "")
                        for item in outcomes
                        if item.get("error_sample")
                    ]
                    logged.append({
                        "source": board_key,
                        "vertical": "career",
                        "started_at": jobspy_started_at,
                        "duration_s": elapsed,
                        "finish_reason": finish_reason,
                        "rows_found": rows_found,
                        "rows_invalid": 0,
                        "error_sample": (
                            f"{failures} of {len(outcomes)} queries failed; {errors[0]}"
                            if errors else ""
                        ),
                    })
                record_scrape_runs(logged)
            except Exception:
                logger.warning("Could not persist JobSpy source health", exc_info=True)

        # Wait for additional scrapers to finish (with timeout to prevent hanging)
        if scraper_thread is not None:
            scraper_thread.join(timeout=120)
            if scraper_thread.is_alive():
                logger.warning("Additional scrapers timed out after 120s — using partial results")
                if progress:
                    progress("Warning: some scrapers timed out, using partial results")
            all_jobs.extend(extra_jobs_result)

        # Publish a structured receipt for EVERY expected career source. This
        # is the contract behind the board's post-run wording: a zero-result
        # source still completed, a partial source names its missing coverage,
        # and a source that vanished from execution is an explicit failure.
        coverage_entries: list[dict[str, Any]] = []
        expected_jobspy = (
            [str(board).strip().lower() for board in jobspy_boards]
            if isinstance(jobspy_boards, list)
            else (["jobspy"] if jobspy_tasks else [])
        )
        for source in expected_jobspy:
            meta = all_scrapers.get(source)
            display = getattr(meta, "display_name", "") or source.replace("_", " ").title()
            coverage_entries.append(
                _source_coverage_entry(
                    source,
                    display,
                    list(jobspy_outcomes.get(source, [])),
                )
            )
        by_additional: dict[str, list[dict[str, Any]]] = {}
        for outcome in additional_outcomes:
            by_additional.setdefault(str(outcome.get("source") or "unknown"), []).append(outcome)
        for source in enabled_names:
            meta = all_scrapers.get(source)
            display = getattr(meta, "display_name", "") or source.replace("_", " ").title()
            coverage_entries.append(
                _source_coverage_entry(
                    source,
                    display,
                    list(by_additional.get(source, [])),
                )
            )
        self._last_source_coverage = _source_coverage_receipt(coverage_entries)

        # Guarantee the contract fields (date_confidence, salary_source,
        # work_type_confidence) on EVERY job. Plugin scrapers already pass
        # through run_scrapers' finalize step, but JobSpy results don't —
        # without this, description-parsed salaries never reach the salary
        # filter and the strict freshness preset can't trust date_confidence.
        from job_finder.tools.scrapers._utils import finalize_scraper_jobs
        finalize_scraper_jobs(all_jobs)

        # Reset funnel for this run
        self._last_funnel = []
        raw_count = len(all_jobs)
        deduped = _deduplicate(all_jobs)
        cross_source = raw_count - len(deduped)
        self._last_pre_filter_count = len(deduped)
        # Funnel stage 1: raw -> deduped
        self._record_funnel_stage(
            "deduped",
            "Cross-source dedup",
            raw_count,
            len(deduped),
        )
        if progress:
            msg = f"Found {len(deduped)} unique jobs (from {raw_count} raw, {cross_source} cross-source duplicates merged)"
            progress(msg)

        # Classify work type and fix is_remote for every job
        if progress:
            progress("Classifying remote/hybrid/onsite...")
        for job in deduped:
            # classify_job_work_type honors ATS-reported remote flags
            # (remote_flag_reported) instead of overriding them with the
            # text heuristic, and yields the confidence contract field.
            wt, wt_confidence = classify_job_work_type(job)
            job["work_type"] = wt
            job["work_type_confidence"] = wt_confidence
            job["is_remote"] = wt == "remote"

        hybrid_count = sum(1 for j in deduped if j["work_type"] == "hybrid")
        remote_count = sum(1 for j in deduped if j["work_type"] == "remote")
        onsite_count = sum(1 for j in deduped if j["work_type"] == "onsite")
        if progress:
            progress(f"Work types: {remote_count} remote, {hybrid_count} hybrid, {onsite_count} onsite")

        # Resolve filter strictness once for the whole filter section.
        # Preset (loose/balanced/strict) with optional per-key overrides.
        filter_settings = _resolve_filter_settings(self.config)

        # Post-search location filter
        # Use explicit location_preferences if configured, otherwise auto-derive
        # from the search locations so filtering always works.
        loc_prefs = self.config.get("location_preferences", {})
        (
            pref_locations, pref_states, pref_cities, pref_places,
            remote_only, include_remote, pref_countries,
        ) = _resolve_location_filter_preferences(
            locations,
            loc_prefs,
        )

        logger.info(
            "Location filter config: filter_enabled=%s, pref_locations=%s, "
            "pref_states=%s, pref_cities=%s, pref_places=%s, remote_only=%s, "
            "include_remote=%s, pref_countries=%s",
            loc_prefs.get("filter_enabled"), pref_locations, pref_states,
            pref_cities, pref_places, remote_only, include_remote, pref_countries,
        )
        if pref_locations or pref_states or pref_cities or pref_places or remote_only or not include_remote:
            pre_count = len(deduped)
            deduped = [
                j for j in deduped
                if location_matches_preferences(
                    j.get("location", ""),
                    j.get("is_remote", False),
                    preferred_states=pref_states,
                    preferred_cities=pref_cities,
                    preferred_locations=pref_locations,
                    remote_only=remote_only,
                    include_remote=include_remote,
                    work_type=j.get("work_type", ""),
                    preferred_places=pref_places,
                    preferred_countries=pref_countries,
                )
            ]
            self._record_funnel_stage("location", "Location filter", pre_count, len(deduped))
            if progress:
                dropped = pre_count - len(deduped)
                progress(f"Location filter: {pre_count} → {len(deduped)} jobs ({dropped} filtered out)")

            # Also purge existing DB records that no longer match location prefs
            try:
                from job_finder.models.database import purge_non_matching_locations
                purged = purge_non_matching_locations(
                    preferred_states=pref_states,
                    preferred_cities=pref_cities,
                    preferred_locations=pref_locations,
                    preferred_places=pref_places,
                    include_remote=include_remote,
                    remote_only=remote_only,
                    preferred_countries=pref_countries,
                    profile=self.profile_name,
                )
                if purged and progress:
                    progress(f"Purged {purged} existing jobs outside preferred locations")
            except Exception as e:
                logger.debug("DB location purge failed (non-fatal): %s", e)
        else:
            self._record_funnel_stage(
                "location", "Location filter", len(deduped), len(deduped), active=False,
            )
            logger.warning("Location filter SKIPPED — no preferences configured")

        # Backfill descriptions for LinkedIn-only jobs that lack them.
        # We skipped linkedin_fetch_description during search for speed. Jobs
        # that appeared on multiple boards already have descriptions from
        # Indeed/Glassdoor via dedup. Only LinkedIn-exclusive jobs (no
        # description at all) need backfilling.
        #
        # This sits AFTER the location gate and BEFORE the salary filter, and
        # both halves of that matter. It used to run before every gate, so a
        # capped budget was spent on jobs the next few filters threw away and
        # the survivors reached the board empty: a real Disney posting showed
        # "REWARD not stated" while its page stated $171,600-$252,000, and the
        # assistant ranked it on title and company alone. It cannot move any
        # later either, or pay that exists only in the description would never
        # reach the floor check below.
        no_desc = [
            j for j in deduped
            if not j.get("description")
            and j.get("url")
            and "linkedin.com" in j.get("url", "")
        ]
        if no_desc:
            # Each LinkedIn description fetch round-trips through their
            # job-detail page; under rate limiting it lands at ~3-5s per
            # request. With 16 workers and a cap of 25 the worst case is
            # ~10-15s. Tunable via search_settings.max_description_backfill.
            try:
                max_backfill = max(0, int(settings.get("max_description_backfill", 25)))
            except (TypeError, ValueError):
                max_backfill = 25
            if len(no_desc) > max_backfill:
                logger.info(
                    "Capping LinkedIn backfill from %d to %d jobs",
                    len(no_desc), max_backfill,
                )
                no_desc = no_desc[:max_backfill]
        if no_desc:
            if progress:
                progress(f"Fetching descriptions for {len(no_desc)} LinkedIn-only jobs...")
            _backfill_linkedin_descriptions(no_desc, max_workers=16)
            # Re-run salary extraction on the freshly fetched descriptions:
            # these jobs had salary_source=None at finalize time.
            finalize_scraper_jobs(no_desc)

        # --- Salary filter: remove jobs with known salary below minimum ---
        # "Known" here means comparable: stated in the user's currency.
        # A minimum is a hard boundary. Strictness may widen role/title
        # matching, but it must never silently lower the number the user set.
        # Missing or different currencies stay eligible as "not comparable".
        salary_floor = _resolve_salary_floor(self.config)
        if salary_floor and salary_floor > 0:
            hard_floor = salary_floor
            target_currency = str(
                (self.config.get("compensation") or {}).get("currency") or ""
            ).strip().upper()
            pre_count = len(deduped)
            deduped = [
                j for j in deduped
                if _job_salary_passes(j, hard_floor, target_currency or None)
            ]
            dropped = pre_count - len(deduped)
            self._record_funnel_stage("salary", "Salary floor", pre_count, len(deduped))
            if dropped and progress:
                progress(f"Salary filter: removed {dropped} jobs below ${hard_floor:,.0f}")
        else:
            self._record_funnel_stage(
                "salary", "Salary floor", len(deduped), len(deduped), active=False,
            )

        # --- Freshness filter: drop postings older than max_days_old ---
        # (keeps jobs with unknown/unparseable dates so we don't over-drop).
        if max_days_old and max_days_old > 0:
            pre_fresh = len(deduped)
            deduped = _filter_jobs_by_freshness(
                deduped,
                max_days_old,
                drop_missing_dates=bool(filter_settings.get("drop_missing_dates", False)),
            )
            dropped = pre_fresh - len(deduped)
            self._record_funnel_stage("freshness", "Freshness filter", pre_fresh, len(deduped))
            if dropped and progress:
                progress(f"Freshness filter: removed {dropped} postings older than {max_days_old} days")
        else:
            self._record_funnel_stage(
                "freshness", "Freshness filter", len(deduped), len(deduped), active=False,
            )

        # --- Level filter: remove jobs too far above or below current level ---
        pre_level = len(deduped)
        deduped = _filter_jobs_by_level(
            deduped,
            self.config.get("career_baseline", {}),
            filters=filter_settings,
            progress=progress,
        )
        career_cfg = self.config.get("career_baseline") or {}
        level_active = bool(
            str(career_cfg.get("current_title", "") or "").strip()
            or str(career_cfg.get("current_level", "") or "").strip()
        )
        self._record_funnel_stage(
            "level", "Level range", pre_level, len(deduped), active=level_active,
        )

        # --- Role relevance filter ---
        pre_role = len(deduped)
        deduped = self.filter_by_role(deduped, filters=filter_settings, progress=progress)
        target_roles = self.config.get("target_roles", [])
        self._record_funnel_stage(
            "role", "Role relevance", pre_role, len(deduped), active=bool(target_roles),
        )

        # --- Staffing agency filter ---
        pre_staffing = len(deduped)
        deduped = self.filter_staffing_agencies(deduped, progress=progress)
        staffing_active = bool(
            (self.config.get("search_settings") or {}).get("exclude_staffing_agencies", False)
        )
        self._record_funnel_stage(
            "staffing", "Staffing agencies", pre_staffing, len(deduped), active=staffing_active,
        )

        # Store the pre-filter count so callers can show a "1,080 → 29" funnel
        self._last_pre_filter_count = getattr(self, '_last_pre_filter_count', len(deduped))
        self._last_post_filter_count = len(deduped)

        return deduped

    # -- Role relevance filter ---------------------------------------------

    def filter_by_role(
        self,
        jobs: list[dict],
        *,
        filters: dict | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Remove jobs whose titles don't match any target role.

        Custom scrapers already filter via ``_match_roles()``, but JobSpy
        results (Indeed, LinkedIn, Glassdoor, etc.) come back unfiltered.
        This catches irrelevant jobs that slipped through — e.g. a nurse
        profile seeing "Lead Software Engineer" because the search term
        "lead nurse practitioner" matched on "lead".

        Confirmed target roles define the primary bucket. AI-expanded roles
        may add a small, explicitly adjacent bucket when primary supply is
        thin, but can never make an off-target result look primary.
        """
        target_roles = list(self.config.get("target_roles", []) or [])
        # When resume analysis was starved and left no target_roles, fall back to
        # the resume's current title so the filter still bites instead of passing
        # the whole noisy pool. Guarded below: this fallback never zeroes the
        # board and never purges the DB (a single guessed title is too weak to
        # delete rows on).
        title_fallback = False
        if not target_roles:
            current_title = str(
                (self.config.get("career_baseline") or {}).get("current_title", "") or ""
            ).strip()
            if not current_title:
                return jobs  # nothing to filter on → pass everything
            target_roles = [current_title]
            title_fallback = True

        from job_finder.tools.scrapers._utils import job_passes_role_filter

        resolved = filters or _resolve_filter_settings(self.config)
        intent_text = " ".join(
            target_roles + list(self.config.get("keyword_searches", []) or [])
        ).lower()
        wants_founding = any(
            term in intent_text
            for term in ("founding", "startup", "early-stage", "early stage", "first hire")
        )
        wants_crypto = any(
            term in intent_text
            for term in ("crypto", "web3", "blockchain", "defi", "solidity", "ethereum")
        )
        include_founding = bool(resolved.get("include_founding_titles", True)) and wants_founding
        match_mode = str(resolved.get("role_match_mode", "all_significant"))
        strictness = str(resolved.get("strictness", _DEFAULT_STRICTNESS))

        # Exact saved-role matches and crypto technical adjacency are separate
        # buckets. The old path let crypto rescue masquerade as "primary",
        # which made a generic platform role indistinguishable from a Data
        # Engineer match. Keep the wider crypto inventory, but label it
        # honestly and order it after confirmed role-family matches.
        pre_count = len(jobs)
        primary = [
            j for j in jobs
            if job_passes_role_filter(
                j, target_roles,
                match_mode=match_mode,
                include_founding=include_founding,
                strictness=strictness,
                allow_crypto_rescue=False,
            )
        ]
        for job in primary:
            job["match_bucket"] = "primary"

        primary_ids = {id(job) for job in primary}
        adjacent: list[dict] = []
        if wants_crypto:
            for job in jobs:
                if id(job) in primary_ids:
                    continue
                if job_passes_role_filter(
                    job,
                    target_roles,
                    match_mode=match_mode,
                    include_founding=include_founding,
                    strictness=strictness,
                    allow_crypto_rescue=True,
                ):
                    job["match_bucket"] = "adjacent"
                    adjacent.append(job)
                    if len(adjacent) >= 100:
                        break

        expanded_roles = list(getattr(self, "_expanded_roles", None) or [])
        if len(primary) < 10 and expanded_roles and len(adjacent) < 100:
            kept_ids = primary_ids | {id(job) for job in adjacent}
            for job in jobs:
                if id(job) in kept_ids:
                    continue
                if job_passes_role_filter(
                    job,
                    expanded_roles,
                    match_mode=match_mode,
                    include_founding=include_founding,
                    strictness=strictness,
                    allow_crypto_rescue=False,
                ):
                    job["match_bucket"] = "adjacent"
                    adjacent.append(job)
                    if len(adjacent) >= 100:
                        break
        filtered = primary + adjacent

        if title_fallback and not filtered:
            # The current-title guess matched nothing: a sourcing gap, not a bad
            # user. Keep the unfiltered set rather than surface an empty board.
            logger.info(
                "Role filter: current-title fallback matched 0/%d jobs; keeping unfiltered",
                pre_count,
            )
            return jobs
        dropped = pre_count - len(filtered)
        if dropped:
            logger.info("Role filter: removed %d/%d jobs not matching target roles", dropped, pre_count)
            if progress:
                progress(f"Role filter: removed {dropped} jobs not matching target roles")

        # Also purge existing DB records that don't match roles — using the SAME
        # matching settings so it can't delete a job filter_by_role just kept.
        # Skipped for the current-title fallback: a single guessed title is too
        # weak a signal to delete stored rows on.
        if not title_fallback:
            try:
                from job_finder.models.database import purge_non_matching_roles
                purge_roles = list(dict.fromkeys(target_roles + expanded_roles))
                purged = purge_non_matching_roles(
                    target_roles=purge_roles,
                    profile=self.profile_name,
                    workspace_id=(self.config.get("workspace") or {}).get("workspace_id"),
                    match_mode=match_mode,
                    include_founding=include_founding,
                    strictness=strictness,
                    allow_crypto_rescue=wants_crypto,
                )
                if purged and progress:
                    progress(f"Purged {purged} existing jobs not matching target roles")
            except Exception as e:
                logger.debug("DB role purge failed (non-fatal): %s", e)

        return filtered

    # -- Staffing agency filter -------------------------------------------

    # Compatibility alias for callers/tests that inspected the old class set.
    _STAFFING_AGENCIES: set[str] = set(STAFFING_AGENCY_NAMES)

    def filter_staffing_agencies(
        self,
        jobs: list[dict],
        *,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Remove jobs posted by known staffing/recruitment agencies.

        Reads ``search_settings.exclude_staffing_agencies`` from config.
        Returns the (possibly filtered) list.
        """
        settings = self.config.get("search_settings") or {}
        if not settings.get("exclude_staffing_agencies", False):
            return jobs

        pre_count = len(jobs)
        filtered = [
            j for j in jobs
            if not self._is_staffing_agency(j.get("company", ""))
        ]
        dropped = pre_count - len(filtered)
        if dropped:
            logger.info("Staffing agency filter: removed %d jobs", dropped)
            if progress:
                progress(f"Staffing agency filter: removed {dropped} jobs from recruitment agencies")
        return filtered

    @classmethod
    def _is_staffing_agency(cls, company: str) -> bool:
        """Return True if *company* matches a known staffing agency (case-insensitive)."""
        return is_staffing_agency(company)

    # -- Stage 2: Resume parsing (no LLM) ---------------------------------

    def set_resume_text(self, text: str) -> None:
        """Pre-load resume text so the pipeline skips file-based lookup."""
        self._preloaded_resume_text = text

    def require_preloaded_resume(self) -> None:
        """Block file-based resume fallback (for hosted/multi-user mode).

        After calling this, ``get_resume_text`` will return an error
        instead of scanning the shared ``knowledge/`` directory.
        """
        self._preloaded_resume_text = self._preloaded_resume_text or ""

    def get_resume_text(self, path: str = "") -> str:
        """Return the full text of the candidate's resume."""
        if self._preloaded_resume_text is not None:
            if self._preloaded_resume_text:
                return self._preloaded_resume_text
            return "ERROR: No resume uploaded. Please upload your resume in Settings."
        if not path:
            path = self.config.get("profile", {}).get("resume_path", "")
        return parse_resume(path, profile=self.profile_name)

    # -- Stage 3: Scoring --------------------------------------------------

    def score_job_with_ai(self, job: dict, resume_text: str) -> dict | None:
        """Score a single job using the LLM. Returns None if unavailable.

        Hits the per-job disk cache first (provider-agnostic). On miss,
        routes to the Anthropic native SDK path with prompt caching when
        available, else the OpenAI-compatible path.
        """
        if not self.llm or not self.llm.is_configured:
            return None

        workspace_id = (self.config.get("workspace") or {}).get("workspace_id")
        scoring_cfg = self.config.get("scoring") or {}
        key = ai_score_cache_key(workspace_id, resume_text, job, scoring_cfg)
        cached = load_cached_ai_score(key)
        if cached:
            # Stamp here too: entries cached before provenance shipped lack it.
            cached["score_source"] = "ai"
            return cached

        user_msg = JD_SCORER_USER_TEMPLATE.format(
            resume_text=_wrap_untrusted("resume", resume_text),
            job_title=_wrap_untrusted("job_title", job.get("title", "")),
            company=_wrap_untrusted("company", job.get("company", "")),
            location=_wrap_untrusted("location", job.get("location", "")),
            job_description=_wrap_untrusted("job_description", job.get("description", "")),
        )
        scorer_prompt = build_scorer_prompt(self.config)

        if self.llm._is_anthropic_provider():
            result = self.llm.chat_json_anthropic_cached(
                scorer_prompt, user_msg, cache_prefix_in_user=resume_text,
            )
        else:
            result = self.llm.chat_json(scorer_prompt, user_msg)

        if isinstance(result, dict) and result:
            result["score_source"] = "ai"
            save_cached_ai_score(key, result)
        return result

    def score_jobs(
        self,
        jobs: list[dict],
        resume_text: str,
        use_ai: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Score all jobs — AI-first when LLM is available.

        When LLM is configured:
          AI scores ALL jobs in parallel. The LLM understands any profession
          (nursing, engineering, marketing, etc.) without hardcoded keywords.
          Keyword scoring is skipped entirely.

        When no LLM:
          Falls back to keyword scoring using the profile's YAML keywords
          (not hardcoded defaults), so non-tech profiles still get reasonable
          scores from their own domain keywords.

        Each job dict is *mutated* to include score fields.
        """
        # Pass 0: Classify companies so tier baselines inform scoring
        for job in jobs:
            if "company_type" not in job:
                job["company_type"] = classify_company(
                    job.get("company", ""),
                    job.get("funding_stage"),
                    job.get("total_funding"),
                    job.get("employee_count"),
                    source_category=_source_category(job.get("source")),
                )

        ai_available = use_ai and self.llm and self.llm.is_configured
        settings = self.config.get("search_settings") or {}

        # Hosted managed-AI keeps per-job scoring on keywords so many concurrent
        # searches can't drain the shared platform LLM that the one-shot resume
        # analysis needs to set target_roles. ai_score_top_n is NOT this lever
        # (<=0 there means "AI-score every job"); ai_score_jobs is.
        if ai_available and settings.get("ai_score_jobs", True):
            ai_score_top_n = int(settings.get("ai_score_top_n", 60) or 0)
            if ai_score_top_n > 0 and len(jobs) > ai_score_top_n:
                if progress:
                    progress(
                        f"Keyword pre-scoring {len(jobs)} jobs to shortlist top "
                        f"{ai_score_top_n} for AI review..."
                    )
                self._score_jobs_keyword(
                    jobs,
                    resume_text,
                    progress=None,
                    emit_summary=False,
                )
                shortlisted = jobs[:ai_score_top_n]
                self._score_jobs_ai(
                    shortlisted,
                    resume_text,
                    progress,
                    total_jobs=len(jobs),
                    emit_summary=False,
                )
                jobs.sort(key=lambda j: j.get("overall_score", 0), reverse=True)
                self._emit_scoring_summary(jobs, progress)
                return jobs
            return self._score_jobs_ai(jobs, resume_text, progress)
        else:
            return self._score_jobs_keyword(jobs, resume_text, progress)

    def _emit_scoring_summary(
        self,
        jobs: list[dict],
        progress: Callable[[str], None] | None = None,
        *,
        prefix: str = "Scoring done",
    ) -> None:
        """Emit a concise scoring summary for the current job set."""
        above_55 = sum(1 for j in jobs if (j.get("overall_score") or 0) >= 55)
        above_40 = sum(1 for j in jobs if (j.get("overall_score") or 0) >= 40)
        if progress:
            progress(f"{prefix}: {above_55} strong matches, {above_40} worth reviewing")

    def _reapply_location_filter_after_ai(
        self,
        jobs: list[dict],
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Re-check location eligibility after AI updates work_type/is_remote.

        Job boards frequently label hybrid roles as remote. We already filter by
        location once before scoring, but if AI later corrects a job from remote
        to hybrid/onsite we need to re-run the same location gate or those jobs
        leak back into the final saved results.
        """
        # Read and clear the transient AI-downgrade marks up front, so they never
        # reach the saved record even on the early return below. A downgraded row
        # forfeits the nationwide bare-country rescue; an untouched row keeps it.
        downgraded_ids = {id(j) for j in jobs if j.pop("_ai_downgraded", False)}
        loc_prefs = self.config.get("location_preferences", {})
        (
            pref_locations, pref_states, pref_cities, pref_places,
            remote_only, include_remote, pref_countries,
        ) = _resolve_location_filter_preferences(
            self.config.get("locations", []),
            loc_prefs,
        )
        if not (pref_locations or pref_states or pref_cities or pref_places or remote_only or not include_remote):
            return jobs

        filtered = []
        for job in jobs:
            if location_matches_preferences(
                job.get("location", ""),
                job.get("is_remote", False),
                preferred_states=pref_states,
                preferred_cities=pref_cities,
                preferred_locations=pref_locations,
                remote_only=remote_only,
                include_remote=include_remote,
                work_type=job.get("work_type", ""),
                preferred_places=pref_places,
                preferred_countries=pref_countries,
                nationwide_ok=id(job) not in downgraded_ids,
            ):
                filtered.append(job)
        dropped = len(jobs) - len(filtered)
        if dropped and progress:
            progress(
                f"  Removed {dropped} jobs after AI updated remote vs local location details"
            )
        return filtered

    def _score_jobs_ai(
        self,
        jobs: list[dict],
        resume_text: str,
        progress: Callable[[str], None] | None = None,
        *,
        total_jobs: int | None = None,
        emit_summary: bool = True,
    ) -> list[dict]:
        """AI-first scoring: LLM scores ALL jobs in parallel.

        The LLM scorer prompt is profile-aware — it reads the profile's
        keywords, weights, compensation targets, and career baseline.
        It works for any profession without hardcoded signal lists.
        """
        if progress:
            if total_jobs and total_jobs != len(jobs):
                progress(
                    f"AI-scoring top {len(jobs)} of {total_jobs} shortlisted jobs "
                    "in parallel..."
                )
            else:
                progress(f"AI-scoring {len(jobs)} jobs in parallel...")

        def _score_one(job: dict) -> tuple[dict, dict | None]:
            return job, self.score_job_with_ai(job, resume_text)

        done = 0
        work_type_corrections = 0
        failed = 0
        # max_workers configurable via search_settings.ai_scoring_workers.
        # 16 is safely below provider rate limits while ~2× the prior 8.
        ai_workers = int(
            (self.config.get("search_settings") or {}).get("ai_scoring_workers", 16) or 16
        )
        ai_workers = max(1, min(ai_workers, 32))
        with ThreadPoolExecutor(max_workers=ai_workers) as pool:
            futures = {pool.submit(_score_one, j): j for j in jobs}
            for future in as_completed(futures):
                try:
                    job, ai_score = future.result()
                except Exception as e:
                    # Out of tokens / provider error: keyword-score this job so it
                    # is never left unscored (an unscored job sorts at random, the
                    # exact "results aren't the greatest" symptom when a shared
                    # quota is exhausted mid-search).
                    logger.warning("AI scoring failed for a job: %s", e)
                    self._keyword_score_single(futures[future], resume_text)
                    failed += 1
                    continue
                done += 1
                if ai_score:
                    # Check if AI corrected the work type
                    ai_wt = ai_score.get("work_type")
                    was_remote = bool(job.get("is_remote")) or job.get("work_type") == "remote"
                    if ai_wt in ("remote", "hybrid", "onsite") and ai_wt != job.get("work_type"):
                        work_type_corrections += 1
                        logger.info(
                            "AI corrected work type for %s @ %s: %s → %s",
                            job.get("title"), job.get("company"),
                            job.get("work_type"), ai_wt,
                        )
                    job.update(ai_score)
                    # Keep work_type / is_remote consistent
                    if ai_wt in ("remote", "hybrid", "onsite"):
                        job["work_type"] = ai_wt
                        job["is_remote"] = ai_wt == "remote"
                        # Remote-washing unmasked: a row admitted as remote that
                        # AI now calls hybrid/onsite must not keep its nationwide
                        # "United States" rescue in the recheck, since it really
                        # needs an office. A row that was never remote (a genuine
                        # nationwide onsite posting) keeps the rescue.
                        if ai_wt in ("hybrid", "onsite") and was_remote:
                            job["_ai_downgraded"] = True
                else:
                    # LLM returned None — fall back to keyword scoring for this job
                    self._keyword_score_single(job, resume_text)
                    failed += 1
                if progress and (done % 10 == 0 or done == len(jobs)):
                    if total_jobs and total_jobs != len(jobs):
                        progress(f"  AI-scored {done}/{len(jobs)} shortlisted jobs")
                    else:
                        progress(f"  AI-scored {done}/{len(jobs)} jobs")

        if work_type_corrections and progress:
            progress(f"  AI corrected work type for {work_type_corrections} jobs")
        if failed and progress:
            progress(f"  {failed} jobs fell back to keyword scoring")

        if work_type_corrections:
            jobs = self._reapply_location_filter_after_ai(jobs, progress)

        jobs.sort(key=lambda j: j.get("overall_score", 0), reverse=True)

        if emit_summary:
            self._emit_scoring_summary(jobs, progress)

        return jobs

    def _score_jobs_keyword(
        self,
        jobs: list[dict],
        resume_text: str,
        progress: Callable[[str], None] | None = None,
        *,
        emit_summary: bool = True,
    ) -> list[dict]:
        """Keyword fallback: scores all jobs using profile keywords + TF-IDF.

        Used when no LLM is configured. Reads keywords from the profile
        YAML so non-tech profiles get domain-appropriate scoring.
        """
        # LLM company intel for known companies (parallel, cached)
        company_intel_cache: dict[str, dict[str, float]] = {}

        if progress:
            progress(f"Keyword-scoring {len(jobs)} jobs (no LLM configured)...")
        for i, job in enumerate(jobs, 1):
            self._keyword_score_single(job, resume_text, company_intel_cache)
            if progress and (i % 100 == 0 or i == len(jobs)):
                progress(f"  Scored {i}/{len(jobs)} jobs")

        jobs.sort(key=lambda j: j.get("overall_score", 0), reverse=True)

        if emit_summary and progress:
            above_40 = sum(1 for j in jobs if (j.get("overall_score") or 0) >= 40)
            above_55 = sum(1 for j in jobs if (j.get("overall_score") or 0) >= 55)
            progress(
                f"Keyword-score done: {above_55} strong matches, {above_40} worth "
                f"reviewing, {len(jobs) - above_40} filtered out"
            )

        return jobs

    def _keyword_score_single(
        self,
        job: dict,
        resume_text: str,
        company_intel_cache: dict[str, dict[str, float]] | None = None,
    ) -> None:
        """Apply keyword-based scoring to a single job (mutates in place)."""
        co_baselines = None
        if company_intel_cache:
            co_baselines = company_intel_cache.get(
                normalize_company_key(job.get("company", ""))
            )
        score_data = score_job_basic(
            job_description=job.get("description", ""),
            resume_text=resume_text,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            company_type=job.get("company_type", "Unknown"),
            salary_min=job.get("salary_min"),
            salary_max=job.get("salary_max"),
            salary_period=job.get("salary_period", ""),
            is_remote=job.get("is_remote", False),
            config=self.config,
            company_baselines=co_baselines,
        )
        job.update(score_data)

    # -- Stage 4: Resume optimization (LLM only) --------------------------

    def optimize_resume(self, job: dict, resume_text: str) -> dict | None:
        """Generate tailored resume tweaks. Returns None without LLM."""
        if not self.llm or not self.llm.is_configured:
            return None

        user_msg = RESUME_OPTIMIZER_USER_TEMPLATE.format(
            resume_text=_wrap_untrusted("resume", resume_text),
            job_title=_wrap_untrusted("job_title", job.get("title", "")),
            company=_wrap_untrusted("company", job.get("company", "")),
            job_description=_wrap_untrusted("job_description", job.get("description", "")),
            overall_score=job.get("overall_score", "N/A"),
            key_strengths=json.dumps(job.get("key_strengths", [])),
            key_gaps=json.dumps(job.get("key_gaps", [])),
        )
        resume_prompt = build_resume_optimizer_prompt(self.config)
        return self.llm.chat_json(resume_prompt, user_msg)

    # -- Stage 5: Cover letter (LLM only) ---------------------------------

    def write_cover_letter(self, job: dict, resume_text: str) -> dict | None:
        """Draft a tailored cover letter. Returns None without LLM."""
        if not self.llm or not self.llm.is_configured:
            return None

        user_msg = COVER_LETTER_USER_TEMPLATE.format(
            resume_text=_wrap_untrusted("resume", resume_text),
            job_title=_wrap_untrusted("job_title", job.get("title", "")),
            company=_wrap_untrusted("company", job.get("company", "")),
            location=_wrap_untrusted("location", job.get("location", "")),
            job_description=_wrap_untrusted("job_description", job.get("description", "")),
        )
        cl_prompt = build_cover_letter_prompt(self.config)
        return self.llm.chat_json(cl_prompt, user_msg)

    # -- Profile generation (LLM only, called once on resume upload) ------

    def generate_profile_from_resume(
        self,
        resume_text: str,
        available_scrapers: list[str] | None = None,
        available_templates: list[str] | None = None,
    ) -> dict | None:
        """Generate a tailored search profile from a candidate's resume.

        This is the load-bearing piece of "any career, any niche". Instead
        of forcing the user to pick from the seven hardcoded archetype
        templates, we ask the LLM to read the resume and produce a profile
        specifically for them — covering niches we never modeled (climate
        tech, vet med, MTS at frontier labs, biotech regulatory, etc.).

        The output schema mirrors the YAML archetype shape, so the same
        ``apply_archetype()`` merge logic in profiles/archetypes.py can
        consume it. The frontend treats a generated profile as a drop-in
        replacement for a hardcoded template — the only difference is the
        confidence + reasoning fields, which expose the LLM's introspection.

        Returns ``None`` when the LLM is unavailable so the caller can
        gracefully fall back to template-based defaults. The result is
        validated against the ``GeneratedProfile`` Pydantic schema before
        being returned — invalid output (wrong shape, weights that don't
        sum, hallucinated scrapers) is treated as a failure and returns
        None rather than corrupting the user's profile.
        """
        if not self.llm or not self.llm.is_configured:
            return None

        # Default available_scrapers to the live registry so the LLM can't
        # hallucinate sources we don't actually run. Imported lazily to
        # avoid a circular at module load.
        if available_scrapers is None:
            try:
                from job_finder.tools.scrapers._registry import get_registry
                available_scrapers = sorted(get_registry().keys())
                # Plus the JobSpy boards which are not registered as plugins
                # but are first-class search sources.
                for jobspy in ("indeed", "linkedin", "glassdoor", "zip_recruiter", "google"):
                    if jobspy not in available_scrapers:
                        available_scrapers.append(jobspy)
            except Exception:
                available_scrapers = []

        if available_templates is None:
            try:
                from job_finder.profiles.archetypes import list_archetypes
                available_templates = [a.slug for a in list_archetypes()]
            except Exception:
                available_templates = []

        user_msg = GENERATE_PROFILE_USER_TEMPLATE.format(
            available_scrapers=", ".join(available_scrapers) or "(none — registry empty)",
            available_templates=", ".join(available_templates) or "(none)",
            resume_text=_wrap_untrusted("resume", resume_text),
        )
        system_prompt = build_generate_profile_prompt(self.config)

        # Generous max_tokens — the schema has 12+ fields and the keyword
        # lists alone can be ~150 tokens. Set high enough that the model
        # never has to truncate the JSON.
        raw = self.llm.chat_json(system_prompt, user_msg, max_tokens=6144)
        if raw is None:
            logger.warning("generate_profile_from_resume: LLM returned None")
            return None

        # Validate via the Pydantic schema. Any shape mismatch (wrong types,
        # missing required fields, weights that don't sum) bounces here and
        # the caller falls back to template-based defaults.
        try:
            from job_finder.models.schemas import GeneratedProfile
            profile = GeneratedProfile.model_validate(raw)
        except Exception as exc:
            logger.warning("generate_profile_from_resume: schema validation failed: %s", exc)
            return None

        # Hard rule: scoring weights must sum to ~1.0. Reject (and log) if
        # the LLM returned malformed weights so we don't silently corrupt
        # the user's profile.
        weights_sum = (
            profile.scoring.technical_skills
            + profile.scoring.leadership_signal
            + profile.scoring.career_progression
            + profile.scoring.platform_building
            + profile.scoring.comp_potential
            + profile.scoring.company_trajectory
            + profile.scoring.culture_fit
        )
        if not 0.98 <= weights_sum <= 1.02:
            logger.warning(
                "generate_profile_from_resume: scoring weights sum to %.3f, not 1.0 — rejecting",
                weights_sum,
            )
            return None

        # Hard rule: enabled_scrapers must be a subset of available. Strip
        # any hallucinated names rather than rejecting the whole profile.
        if available_scrapers:
            profile.enabled_scrapers = [
                s for s in profile.enabled_scrapers if s in available_scrapers
            ]

        return profile.model_dump()

    # -- Stage 5b: Evaluation report (LLM only) ---------------------------

    def generate_evaluation_report(self, job: dict, resume_text: str) -> dict | None:
        """Produce a structured per-job evaluation report.

        Walks through each JD requirement and maps it to exact quotes from
        the candidate's resume (Block B in career-ops parlance), plus
        archetype detection, recommended framing, and red flags. This is the
        artifact the user reads before deciding to apply — not a sort key.

        Returns None when the LLM is unavailable so the pipeline continues
        to work without deep evaluation.
        """
        if not self.llm or not self.llm.is_configured:
            return None

        user_msg = EVALUATION_REPORT_USER_TEMPLATE.format(
            resume_text=_wrap_untrusted("resume", resume_text),
            job_title=_wrap_untrusted("job_title", job.get("title", "")),
            company=_wrap_untrusted("company", job.get("company", "")),
            location=_wrap_untrusted("location", job.get("location", "")),
            job_description=_wrap_untrusted("job_description", job.get("description", "")),
            overall_score=job.get("overall_score", "N/A"),
            recommendation=job.get("recommendation", "N/A"),
            key_strengths=json.dumps(job.get("key_strengths", [])),
            key_gaps=json.dumps(job.get("key_gaps", [])),
        )
        eval_prompt = build_evaluation_report_prompt(self.config)
        # Reports can be long — STAR+R reflections, per-requirement evidence,
        # recommended framing. Give the model room to produce the full object.
        return self.llm.chat_json(eval_prompt, user_msg, max_tokens=6144)

    # -- Stage 6: Company research (LLM only) -----------------------------

    def research_company(
        self, company_name: str, job_title: str = "", fast: bool = False,
    ) -> dict | None:
        """Build a company intelligence profile grounded with live web search.

        Flow: web search → inject results into LLM prompt → structured JSON.
        Falls back to LLM-only if web search is unavailable.
        When ``fast=True``, only runs 2 web queries instead of 4.
        Returns None without LLM.
        """
        if not self.llm or not self.llm.is_configured:
            return None

        # Try web search for real-time grounding
        web_context = ""
        try:
            from job_finder.tools.web_search import search_company

            ctx = search_company(company_name, job_title, fast=fast)
            if ctx.total_results > 0:
                web_context = ctx.format_for_prompt(max_chars=6000)
                logger.info(
                    "Web search grounding for %s: %d results",
                    company_name,
                    ctx.total_results,
                )
        except Exception as e:
            logger.debug("Web search unavailable for %s: %s", company_name, e)

        # Use grounded template when we have web results, plain template otherwise.
        # Even company_name is wrapped because a malicious scraped row could
        # have a company name like "Acme</company_name><instruction>...".
        if web_context:
            user_msg = COMPANY_RESEARCHER_GROUNDED_USER_TEMPLATE.format(
                company_name=_wrap_untrusted("company_name", company_name),
                job_title=_wrap_untrusted("job_title", job_title),
                web_context=_wrap_untrusted("web_results", web_context),
            )
        else:
            user_msg = COMPANY_RESEARCHER_USER_TEMPLATE.format(
                company_name=_wrap_untrusted("company_name", company_name),
                job_title=_wrap_untrusted("job_title", job_title),
            )

        cr_prompt = build_company_researcher_prompt(self.config)
        return self.llm.chat_json(cr_prompt, user_msg)

    # -- Stage 7: Auto-apply (opt-in) -------------------------------------

    def prepare_application_kits(
        self,
        jobs: list[dict],
        resume_path: str = "",
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Prepare application kits for STRONG_APPLY jobs with known ATS routes.

        Questboard never transmits an application (docs/anti-slop.md);
        this stage prefills everything so the human sends it in seconds.
        Respects ``auto_apply.enabled`` as the prepare-kits switch.
        """
        from job_finder.tools.auto_apply_tool import prepare_application_kit

        apply_config = self.config.get("auto_apply", {})
        if not apply_config.get("enabled", False):
            if progress:
                progress("Application kits are disabled in config")
            return jobs

        candidates = [
            j for j in jobs
            if j.get("recommendation") == "STRONG_APPLY"
        ]
        if progress:
            progress(f"Application kits: {len(candidates)} STRONG_APPLY candidates")

        kits = 0
        for job in candidates:
            result = prepare_application_kit(
                job=job,
                config=self.config,
                resume_path=resume_path,
                cover_letter_text=job.get("cover_letter", ""),
            )
            if not result.get("success"):
                continue
            job["application_kit"] = {
                "method": result["method"],
                "apply_url": result.get("apply_url", ""),
                "fields": result.get("fields", {}),
            }
            kits += 1
            if progress:
                progress(
                    f"  Kit ready for {job.get('company', '')} via {result['method']}"
                )

        if progress:
            progress(f"Application kits complete: {kits} ready; you send them")

        return jobs

    # -- Full pipeline -----------------------------------------------------

    def run_full_pipeline(
        self,
        progress: Callable[[str], None] | None = None,
        roles: list[str] | None = None,
        locations: list[str] | None = None,
        use_ai: bool = True,
        enhance: bool = True,
        search_run_id: str | None = None,
    ) -> list[dict]:
        """Execute the complete pipeline: search -> score -> enhance -> save -> auto-apply.

        Parameters
        ----------
        progress : callable, optional
            Function accepting a status string for UI updates.
        roles, locations : list, optional
            Override the defaults from search_config.yaml.
        use_ai : bool
            If True *and* an LLM is connected, use AI scoring / generation.
            If False, only basic keyword scoring is used.
        enhance : bool
            If True *and* use_ai is True, generate resume tweaks, cover letters,
            and company intel for top matches. If False, only AI scoring runs.

        Returns
        -------
        list[dict]
            The scored (and optionally enhanced) job list.
        """
        init_db()

        # 1. Search
        jobs = self.search_all_jobs(roles=roles, locations=locations, progress=progress)
        if not jobs:
            if progress:
                progress("No jobs found. Try broadening your search criteria.")
            return []

        # Work type classification + location filter already done inside search_all_jobs()

        # 2. Parse resume
        if progress:
            progress("Parsing resume...")
        resume_text = self.get_resume_text()
        has_resume = not resume_text.startswith("ERROR")

        # 3. Score
        if has_resume:
            if progress:
                progress("Scoring jobs against resume...")
            jobs = self.score_jobs(jobs, resume_text, use_ai=use_ai, progress=progress)
        else:
            if progress:
                progress("No resume found -- skipping scoring")

        rank_enabled = bool(
            (self.config.get("search_settings") or {}).get("hybrid_ranking_enabled", False)
        )
        rank_query = ""
        if rank_enabled:
            from job_finder.hybrid_ranker import rank_jobs

            rank_query = "\n".join(
                [
                    *list(self.config.get("target_roles", []) or []),
                    *list(self.config.get("keyword_searches", []) or []),
                    str((self.config.get("career_baseline") or {}).get("current_title", "")),
                ]
            ).strip()
            if not rank_query and has_resume:
                rank_query = resume_text[:4000]
            jobs = rank_jobs(jobs, query_text=rank_query, config=self.config)

        # 4. Enhance top jobs (AI only, when enhance=True)
        ai_available = (
            use_ai
            and enhance
            and (self.config.get("search_settings") or {}).get("ai_enhance_jobs", True)
            and self.llm
            and self.llm.is_configured
        )
        max_enhance = self.config.get("search_settings", {}).get("max_enhance", 10)
        strong = [j for j in jobs if j.get("recommendation") in ("STRONG_APPLY", "APPLY")][:max_enhance]
        enhanced_count = 0

        if ai_available and has_resume and strong:
            if progress:
                progress(f"Enhancing top {len(strong)} jobs with AI in parallel...")

            def _enhance_one(idx_job: tuple[int, dict]) -> bool:
                i, job = idx_job
                if progress:
                    progress(f"  Enhancing {i}/{len(strong)}: {job.get('company', '')}")

                # Run all 4 LLM calls for this job in parallel. The evaluation
                # report is the biggest call (walks every JD requirement) but
                # we only run it for STRONG_APPLY jobs to keep cost bounded.
                tweaks = None
                cl = None
                intel = None
                report = None

                def _get_tweaks() -> None:
                    nonlocal tweaks
                    if job.get("recommendation") == "STRONG_APPLY":
                        tweaks = self.optimize_resume(job, resume_text)

                def _get_cover_letter() -> None:
                    nonlocal cl
                    if job.get("recommendation") == "STRONG_APPLY":
                        cl = self.write_cover_letter(job, resume_text)

                def _get_intel() -> None:
                    nonlocal intel
                    intel = self.research_company(
                        job.get("company", ""), job.get("title", ""), fast=True
                    )

                def _get_report() -> None:
                    nonlocal report
                    if job.get("recommendation") == "STRONG_APPLY":
                        report = self.generate_evaluation_report(job, resume_text)

                with ThreadPoolExecutor(max_workers=4) as inner_pool:
                    inner_futures = [
                        inner_pool.submit(_get_tweaks),
                        inner_pool.submit(_get_cover_letter),
                        inner_pool.submit(_get_intel),
                        inner_pool.submit(_get_report),
                    ]
                    for f in inner_futures:
                        f.result()

                # Apply results to job dict (safe — each job dict is unique)
                if tweaks:
                    job["resume_tweaks_json"] = json.dumps(tweaks)
                if cl:
                    job["cover_letter"] = cl.get("cover_letter_text", "")
                if intel:
                    job["company_intel_json"] = json.dumps(intel)
                    job["funding_stage"] = intel.get("funding_stage", "")
                    job["total_funding"] = intel.get("total_funding", "")
                    job["employee_count"] = intel.get("employee_count", "")
                if report:
                    job["evaluation_report_json"] = json.dumps(report)

                return bool(tweaks or cl or intel or report)

            # Parallelize across jobs (cap at 5 for speed vs rate limits)
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {
                    pool.submit(_enhance_one, (i, job)): job
                    for i, job in enumerate(strong, 1)
                }
                for future in as_completed(futures):
                    try:
                        if future.result():
                            enhanced_count += 1
                    except Exception as e:
                        logger.warning("Enhancement failed (non-fatal): %s", e)

        # 5. Save to database
        if progress:
            progress("Saving results to database...")
        saved = 0
        for job in jobs:
            # Company type already classified in scoring phase (Pass 0)
            ct = job.get("company_type") or classify_company(
                job.get("company", ""),
                job.get("funding_stage"),
                job.get("total_funding"),
                job.get("employee_count"),
                source_category=_source_category(job.get("source")),
            )

            rec = save_application(
                job_title=job.get("title", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                job_url=job.get("url", ""),
                source=job.get("source", ""),
                description=job.get("description", ""),
                is_remote=job.get("is_remote", False),
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                salary_currency=job.get("salary_currency", ""),
                salary_period=job.get("salary_period", ""),
                salary_min_annualized=job.get("salary_min_annualized"),
                salary_max_annualized=job.get("salary_max_annualized"),
                salary_source=job.get("salary_source"),
                date_posted=job.get("date_posted"),
                date_confidence=job.get("date_confidence"),
                overall_score=job.get("overall_score"),
                technical_score=job.get("technical_score"),
                leadership_score=job.get("leadership_score"),
                comp_potential_score=job.get("comp_potential_score"),
                platform_building_score=job.get("platform_building_score"),
                company_trajectory_score=job.get("company_trajectory_score"),
                culture_fit_score=job.get("culture_fit_score"),
                career_progression_score=job.get("career_progression_score"),
                recommendation=job.get("recommendation"),
                score_source=job.get("score_source"),
                rank_score=job.get("rank_score"),
                rank_source=job.get("rank_source"),
                match_bucket=job.get("match_bucket"),
                match_reasons=job.get("match_reasons"),
                industry_tags=job.get("industry_tags"),
                ecosystem_tags=job.get("ecosystem_tags"),
                score_reasoning=job.get("score_reasoning"),
                score_evidence=job.get("score_evidence"),
                key_strengths=json.dumps(job.get("key_strengths", [])),
                key_gaps=json.dumps(job.get("key_gaps", [])),
                funding_stage=job.get("funding_stage"),
                total_funding=job.get("total_funding"),
                employee_count=job.get("employee_count"),
                company_intel_json=job.get("company_intel_json"),
                resume_tweaks_json=job.get("resume_tweaks_json"),
                evaluation_report_json=job.get("evaluation_report_json", ""),
                cover_letter=job.get("cover_letter"),
                application_method=job.get("application_method", ""),
                profile=self.profile_name,
                company_type=ct,
                work_type=job.get("work_type", ""),
                search_run_id=search_run_id,
                workspace_id=self.config.get("workspace", {}).get("workspace_id"),
            )
            if rec:
                job["db_id"] = rec.id
                saved += 1

        # Dense work belongs to the search worker, after the scrape/save hot
        # path and against only this run's visible career row IDs. A missing or
        # invalid model artifact keeps the lexical order.
        if rank_enabled and has_resume:
            candidate_ids = [int(job["db_id"]) for job in jobs if job.get("db_id")]
            workspace_id = (self.config.get("workspace") or {}).get("workspace_id")
            semantic_scores: dict[int, float] = {}
            if candidate_ids:
                try:
                    from job_finder import embedder
                    from job_finder.embeddings_index import index_embeddings, load_embeddings

                    index_embeddings(
                        application_ids=candidate_ids,
                        workspace_id=workspace_id,
                    )
                    app_ids, matrix = load_embeddings(
                        application_ids=candidate_ids,
                        workspace_id=workspace_id,
                    )
                    semantic_query = f"{rank_query}\n{resume_text[:12000]}".strip()
                    query_vector = embedder.encode_one(semantic_query, is_query=True)
                    if matrix is not None and query_vector is not None:
                        similarities = matrix @ query_vector
                        semantic_scores = {
                            app_id: float(similarity)
                            for app_id, similarity in zip(app_ids, similarities)
                        }
                except Exception as exc:
                    logger.warning("Semantic ranking unavailable; keeping BM25 order (%s)", exc)

            from job_finder.hybrid_ranker import rank_jobs
            from job_finder.models.database import save_application_ranks

            jobs = rank_jobs(
                jobs,
                query_text=rank_query,
                config=self.config,
                semantic_scores=semantic_scores or None,
            )
            try:
                save_application_ranks(jobs, workspace_id=workspace_id)
            except Exception as exc:
                logger.warning("Could not persist hybrid order (%s)", exc)

        # 6. Application kits (opt-in; nothing is ever transmitted)
        apply_config = self.config.get("auto_apply", {})
        if apply_config.get("enabled", False):
            if progress:
                progress("Preparing application kits for top jobs...")
            resume_path = self.config.get("profile", {}).get("resume_path", "")
            if not resume_path:
                resume_path = find_resume(profile=self.profile_name) or ""
            self.prepare_application_kits(jobs, resume_path=resume_path, progress=progress)

        if progress:
            progress(f"Done! Saved {saved} jobs ({enhanced_count} enhanced with AI)")

        return jobs
