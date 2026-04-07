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
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
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
    JD_SCORER_USER_TEMPLATE,
    RESUME_OPTIMIZER_USER_TEMPLATE,
    build_company_researcher_prompt,
    build_cover_letter_prompt,
    build_resume_optimizer_prompt,
    build_scorer_prompt,
)
from job_finder.company_classifier import (
    classify_company,
    classify_work_type,
    location_matches_preferences,
)
from job_finder.scoring import score_job_basic, get_company_baselines, normalize_company_key
from job_finder.scoring.dimensions import (
    _extract_level,
    resolve_current_level,
)  # re-export for tests/consumers
from job_finder.scoring.helpers import annualize_amount
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


def _normalize_company(name: str) -> str:
    """Normalize a company name for dedup comparison."""
    if not name:
        return ""
    t = name.lower().strip()
    t = unicodedata.normalize("NFKD", t)
    # Remove common corporate suffixes
    for suffix in (
        ", inc.", ", inc", ", llc", ", corp.", ", corp", ", ltd.", ", ltd",
        ", limited", ", co.", " inc.", " inc", " llc", " corp.", " corp",
        " ltd.", " ltd", " limited", " co.", " gmbh", " ag", " plc",
        " sa", " sas", " bv", " s.a.", " s.r.l.",
    ):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    # Strip non-alphanumeric, collapse whitespace
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _normalize_title(title: str) -> str:
    """Normalize a job title for dedup comparison."""
    if not title:
        return ""
    t = title.lower().strip()
    t = unicodedata.normalize("NFKD", t)
    # Remove common level prefixes/suffixes that vary across sources
    t = re.sub(r"\b(sr\.?|senior|jr\.?|junior|lead|principal|staff)\b", lambda m: {
        "sr": "senior", "sr.": "senior", "jr": "junior", "jr.": "junior",
    }.get(m.group(0).lower(), m.group(0).lower()), t)
    # Strip non-alphanumeric, collapse whitespace
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _normalize_location(location: str) -> str:
    """Normalize a location string for dedup comparison."""
    if not location:
        return ""
    t = unicodedata.normalize("NFKD", location.lower().strip())
    if "remote" in t:
        return "remote"
    if "hybrid" in t:
        return "hybrid"
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _normalize_description(text: str) -> str:
    """Normalize descriptions so obviously identical postings cluster together."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text.lower())
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _descriptions_look_duplicate(left: str, right: str) -> bool:
    """Return True only when two descriptions look like the same posting."""
    left_norm = _normalize_description(left)
    right_norm = _normalize_description(right)
    if not left_norm or not right_norm:
        return False

    shorter, longer = sorted((left_norm, right_norm), key=len)
    if len(shorter) >= 120 and shorter in longer:
        return True

    return SequenceMatcher(
        None,
        left_norm[:1600],
        right_norm[:1600],
    ).ratio() >= 0.82


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
    """From a group of duplicate jobs, pick the one with the richest data."""
    def _richness(job: dict) -> tuple:
        desc_len = len(job.get("description") or "")
        has_salary = 1 if (job.get("salary_min") or job.get("salary_max")) else 0
        has_url = 1 if job.get("url") else 0
        # Prefer sources that tend to have richer descriptions
        source_rank = {
            "indeed": 5, "linkedin": 4,
            "greenhouse": 4, "lever": 4, "ashby": 4, "workday": 4,
            "glassdoor": 3, "workatastartup": 3,
            "remotive": 2, "himalayas": 2, "remoteok": 2, "hackernews": 2,
            "weworkremotely": 2, "cryptojobslist": 2, "arbeitnow": 2,
            "themuse": 2, "zip_recruiter": 2, "google": 1,
        }
        src = source_rank.get((job.get("source") or "").lower(), 0)
        return (has_salary, desc_len, has_url, src)

    best = max(group, key=_richness)

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
                break

    return best


def _deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove duplicates while preserving distinct openings.

    When the same job appears from multiple sources (e.g. Indeed, Glassdoor,
    Google Jobs), keeps the version with the richest data and merges salary
    info from siblings. Fuzzy merges only happen when company, title, and
    location all match and the descriptions look materially identical.
    """
    url_groups: dict[str, list[dict]] = {}
    groups: dict[str, list[dict]] = {}
    unique: list[dict] = []

    for job in jobs:
        url = job.get("url", "")
        if url:
            url_groups.setdefault(url, []).append(job)
        else:
            unique.append(job)

    collapsed: list[dict] = []
    for group in url_groups.values():
        collapsed.append(_pick_best_job(group) if len(group) > 1 else group[0])
    collapsed.extend(unique)

    unique = []
    no_key: list[dict] = []
    for job in collapsed:
        company = job.get("company", "")
        title = job.get("title", "")
        location = job.get("location", "")
        if company and title and _normalize_location(location):
            key = _dedup_key(company, title, location)
            groups.setdefault(key, []).append(job)
        else:
            no_key.append(job)

    for group in groups.values():
        if len(group) == 1:
            unique.append(group[0])
            continue

        clusters: list[list[dict]] = []
        for job in group:
            placed = False
            for cluster in clusters:
                if _descriptions_look_duplicate(
                    job.get("description", ""),
                    cluster[0].get("description", ""),
                ):
                    cluster.append(job)
                    placed = True
                    break
            if not placed:
                clusters.append([job])

        for cluster in clusters:
            unique.append(_pick_best_job(cluster) if len(cluster) > 1 else cluster[0])

    unique.extend(no_key)
    return unique


def _resolve_location_filter_preferences(
    locations: list[str],
    loc_prefs: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]], bool, bool]:
    """Resolve post-search location filtering from explicit prefs or raw locations."""
    loc_prefs = loc_prefs or {}
    from job_finder.company_classifier import parse_location as _parse_loc

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
        return (
            preferred_locations,
            preferred_states,
            preferred_cities,
            preferred_places,
            bool(loc_prefs.get("remote_only", False)),
            bool(loc_prefs.get("include_remote", True)),
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

    return pref_locations, pref_states, pref_cities, _derive_place_payloads(pref_locations), remote_only, include_remote


def _filter_jobs_by_level(
    jobs: list[dict],
    career_cfg: dict | None,
    *,
    progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Filter jobs that are too far above or below the configured level."""
    career_cfg = career_cfg or {}
    current_title = str(career_cfg.get("current_title", "") or "").strip()
    current_level_label = str(career_cfg.get("current_level", "") or "").strip()
    if not current_title and not current_level_label:
        return jobs

    current_level = resolve_current_level(career_cfg)
    pre_count = len(jobs)
    if current_level >= 3:
        filtered = [
            job for job in jobs
            if _extract_level(job.get("title", "")) >= current_level - 1.5
        ]
    else:
        filtered = [
            job for job in jobs
            if _extract_level(job.get("title", "")) <= current_level + 2.0
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
                    job["description"] = desc_el.get_text(separator="\n", strip=True)[:3000]
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
        """
        if not self.llm or not self.llm.is_configured:
            return roles
        if not roles:
            return roles

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
        locations = locations or self.config.get("locations", ["Los Angeles, CA"])
        settings = self.config.get("search_settings") or {}
        results_per_board = max(1, settings.get("results_per_board", 50))
        results_per_additional = max(1, settings.get("results_per_additional_source", 100))
        max_days_old = max(1, settings.get("max_days_old", 14))
        search_distance = settings.get("search_radius_miles")  # None = JobSpy default (50 miles)
        jobspy_boards = self.config.get("job_boards") or None  # None → default boards

        # When roles are passed explicitly (e.g. from the API, which already
        # merges keywords into the roles list), don't re-read keyword_searches
        # from config — that would double-count them.
        if roles:
            roles_raw = roles
            keywords_raw: list[str] = []
        else:
            roles_raw = self.config.get("target_roles", [])
            keywords_raw = self.config.get("keyword_searches", [])

        # Consolidate similar search terms to reduce redundant JobSpy queries
        consolidated = _consolidate_search_terms(roles_raw, keywords_raw, config=self.config)

        # Broader queries → more results per query to compensate
        original_count = len(roles_raw) + len(keywords_raw)
        if consolidated and len(consolidated) < original_count:
            ratio = original_count / len(consolidated)
            boost = max(2, int(ratio))
            results_per_board = min(200, results_per_board * boost)
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
        specialty_kw = _get_specialty_keywords(self.config)
        def _query_priority(term: str) -> int:
            """Lower = runs first.  Niche keywords before broad roles."""
            t = term.lower()
            if t in specialty_kw or len(t) <= 4:
                return 0  # tech keywords first ("dbt", "SQL")
            if _HIGH_VALUE_PATTERNS.search(term):
                return 1  # founding/niche roles next
            if " " in t:
                return 2  # multi-word role queries ("data engineer")
            return 3  # single-word broad queries last

        prioritized = sorted(consolidated, key=_query_priority)
        search_tasks: list[tuple[str, str]] = []
        for term in prioritized:
            for loc in locations:
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

        total_tasks = len(search_tasks)
        counter = {"done": 0}
        lock = threading.Lock()
        all_jobs: list[dict] = []
        # Track unique jobs for early stopping
        seen_urls: set[str] = set()
        unique_count = 0
        max_unique = max(100, settings.get("max_unique_jobs", 500))
        stop_early = threading.Event()

        def _search_one(task: tuple[str, str]) -> list[dict]:
            nonlocal unique_count
            # Skip if we already have enough unique jobs
            if stop_early.is_set():
                return []
            term, loc = task
            is_remote = True if loc.lower() == "remote" else None
            jobs = search_jobs(
                search_term=term,
                location=loc if loc.lower() != "remote" else "United States",
                results_wanted=results_per_board,
                hours_old=max_days_old * 24,
                is_remote=is_remote,
                country=settings.get("country", "USA"),
                boards=jobspy_boards,
                # Skip fetching full LinkedIn page per result (~2-3s each).
                # Descriptions still come from Indeed, Glassdoor, Google.
                # LinkedIn results keep title/company/location/salary/URL.
                linkedin_fetch_description=False,
                distance=search_distance,
            )
            with lock:
                if stop_early.is_set():
                    return jobs  # another thread hit the threshold while we were searching
                counter["done"] += 1
                n = counter["done"]
                # Count truly new URLs for early stopping
                new_count = 0
                for j in jobs:
                    url = j.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        new_count += 1
                unique_count += new_count
                if unique_count >= max_unique:
                    stop_early.set()
            if progress:
                sources = ", ".join(set(j.get("source", "?") for j in jobs)) if jobs else "no boards"
                suffix = " (stopping — enough results)" if stop_early.is_set() else ""
                progress(f"  [{n}/{total_tasks}] '{term}' in {loc} → {len(jobs)} results from {sources}{suffix}")
            return jobs

        # --- Launch JobSpy searches + additional scrapers concurrently ---
        if progress:
            progress(f"Searching {total_tasks} role×location combos in parallel...")

        # Cap workers to avoid overwhelming job board servers with concurrent
        # requests.  Each worker hits 5 sites simultaneously, so 6 workers =
        # 30 concurrent requests.  More than that risks IP blocks.
        max_jobspy_workers = min(total_tasks, settings.get("max_parallel_searches", 6))

        # Prepare additional scraper arguments
        enabled_names: list[str] = []
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
                if meta.search_fn is None:
                    continue
                yaml_entry = next(
                    (s for s in extra_sources if s.get("name") == name), None
                )
                if yaml_entry is not None:
                    if yaml_entry.get("enabled", True):
                        enabled_names.append(name)
                elif meta.enabled_by_default:
                    enabled_names.append(name)

            # Build watchlist_by_ats from profile config
            watchlist = self.config.get("watchlist", [])
            watchlist_by_ats: dict[str, list[str]] = {}
            for entry in watchlist:
                ats = entry.get("ats", "")
                slug = entry.get("slug", "")
                if ats and slug and ats != "unknown":
                    watchlist_by_ats.setdefault(ats, []).append(slug)
            # Enable ATS scrapers that have watchlist companies
            for ats_name in watchlist_by_ats:
                if ats_name not in enabled_names and ats_name in all_scrapers:
                    enabled_names.append(ats_name)
        except Exception as e:
            logger.warning("Could not load scraper registry: %s", e)
            watchlist_by_ats = {}

        # Use AI to expand role keywords for better scraper filtering.
        # This helps non-tech profiles (nurse, marketer, etc.) by generating
        # related title keywords the LLM knows about, so scrapers can filter
        # more intelligently beyond just substring matching.
        scraper_roles = self.expand_roles_with_ai(roles_raw, progress=progress)
        # Store expanded roles so filter_by_role uses them too
        self._expanded_roles = scraper_roles

        # Run JobSpy searches in a thread pool, and additional scrapers
        # concurrently in their own thread.
        extra_jobs_result: list[dict] = []

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
        if search_tasks:
            with ThreadPoolExecutor(max_workers=max_jobspy_workers) as pool:
                futures = {pool.submit(_search_one, t): t for t in search_tasks}
                early_stopped = False
                for future in as_completed(futures):
                    try:
                        all_jobs.extend(future.result())
                    except Exception as e:
                        logger.warning("JobSpy search failed (non-fatal): %s", e)
                    # Cancel queued (not yet started) tasks after early stop,
                    # but keep collecting results from already-running tasks.
                    if stop_early.is_set() and not early_stopped:
                        early_stopped = True
                        cancelled = 0
                        for f in futures:
                            if f.cancel():
                                cancelled += 1
                        if cancelled:
                            logger.info("Early stop: cancelled %d queued searches", cancelled)

        # Wait for additional scrapers to finish (with timeout to prevent hanging)
        if scraper_thread is not None:
            scraper_thread.join(timeout=120)
            if scraper_thread.is_alive():
                logger.warning("Additional scrapers timed out after 120s — using partial results")
                if progress:
                    progress("Warning: some scrapers timed out, using partial results")
            all_jobs.extend(extra_jobs_result)

        deduped = _deduplicate(all_jobs)
        cross_source = len(all_jobs) - len(deduped)
        if progress:
            msg = f"Found {len(deduped)} unique jobs (from {len(all_jobs)} raw, {cross_source} cross-source duplicates merged)"
            progress(msg)

        # Backfill descriptions for LinkedIn-only jobs that lack them.
        # We skipped linkedin_fetch_description during search for speed.
        # Jobs that appeared on multiple boards already have descriptions
        # from Indeed/Glassdoor via dedup.  Only LinkedIn-exclusive jobs
        # (no description at all) need backfilling.
        no_desc = [
            j for j in deduped
            if not j.get("description")
            and j.get("url")
            and "linkedin.com" in j.get("url", "")
        ]
        if no_desc:
            # Cap backfill to avoid spending minutes fetching descriptions.
            # 50 jobs × 8 workers ≈ 7 rounds × ~3s = ~20s.
            max_backfill = 50
            if len(no_desc) > max_backfill:
                logger.info(
                    "Capping LinkedIn backfill from %d to %d jobs",
                    len(no_desc), max_backfill,
                )
                no_desc = no_desc[:max_backfill]
            if progress:
                progress(f"Fetching descriptions for {len(no_desc)} LinkedIn-only jobs...")
            _backfill_linkedin_descriptions(no_desc, max_workers=8)

        # Classify work type and fix is_remote for every job
        if progress:
            progress("Classifying remote/hybrid/onsite...")
        for job in deduped:
            wt = classify_work_type(
                job.get("location", ""),
                job.get("description", ""),
                job.get("is_remote", False),
            )
            job["work_type"] = wt
            job["is_remote"] = wt == "remote"

        hybrid_count = sum(1 for j in deduped if j["work_type"] == "hybrid")
        remote_count = sum(1 for j in deduped if j["work_type"] == "remote")
        onsite_count = sum(1 for j in deduped if j["work_type"] == "onsite")
        if progress:
            progress(f"Work types: {remote_count} remote, {hybrid_count} hybrid, {onsite_count} onsite")

        # Post-search location filter
        # Use explicit location_preferences if configured, otherwise auto-derive
        # from the search locations so filtering always works.
        loc_prefs = self.config.get("location_preferences", {})
        pref_locations, pref_states, pref_cities, pref_places, remote_only, include_remote = _resolve_location_filter_preferences(
            locations,
            loc_prefs,
        )

        logger.info(
            "Location filter config: filter_enabled=%s, pref_locations=%s, "
            "pref_states=%s, pref_cities=%s, pref_places=%s, remote_only=%s, include_remote=%s",
            loc_prefs.get("filter_enabled"), pref_locations, pref_states,
            pref_cities, pref_places, remote_only, include_remote,
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
                )
            ]
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
                    profile=self.profile_name,
                )
                if purged and progress:
                    progress(f"Purged {purged} existing jobs outside preferred locations")
            except Exception as e:
                logger.debug("DB location purge failed (non-fatal): %s", e)
        else:
            logger.warning("Location filter SKIPPED — no preferences configured")

        # --- Salary filter: remove jobs with known salary below minimum ---
        comp_cfg = self.config.get("compensation", {})
        min_base = annualize_amount(
            comp_cfg.get("min_base", 0),
            comp_cfg.get("pay_period", "annual"),
        ) or 0
        if min_base and min_base > 0:
            # Allow 30% flex (e.g. min $190K filters out jobs < $133K)
            hard_floor = min_base * 0.7
            pre_count = len(deduped)
            deduped = [
                j for j in deduped
                if not (j.get("salary_max_annualized") or j.get("salary_max"))
                or (j.get("salary_max_annualized") or j.get("salary_max")) >= hard_floor
            ]
            dropped = pre_count - len(deduped)
            if dropped and progress:
                progress(f"Salary filter: removed {dropped} jobs below ${hard_floor:,.0f}")

        # --- Level filter: remove jobs too far above or below current level ---
        deduped = _filter_jobs_by_level(
            deduped,
            self.config.get("career_baseline", {}),
            progress=progress,
        )

        # --- Role relevance filter ---
        deduped = self.filter_by_role(deduped, progress=progress)

        # --- Staffing agency filter ---
        deduped = self.filter_staffing_agencies(deduped, progress=progress)

        return deduped

    # -- Role relevance filter ---------------------------------------------

    def filter_by_role(
        self,
        jobs: list[dict],
        *,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Remove jobs whose titles don't match any target role.

        Custom scrapers already filter via ``_match_roles()``, but JobSpy
        results (Indeed, LinkedIn, Glassdoor, etc.) come back unfiltered.
        This catches irrelevant jobs that slipped through — e.g. a nurse
        profile seeing "Lead Software Engineer" because the search term
        "lead nurse practitioner" matched on "lead".

        Uses the same ``_match_roles()`` logic as the scrapers for consistency.
        When AI-expanded roles are available (from ``expand_roles_with_ai``),
        those are used instead — they include related titles the LLM knows
        about (e.g. "APRN" for a nurse profile) so legitimate jobs aren't
        filtered out.
        """
        # Prefer AI-expanded roles (set by search_all_jobs) over raw config
        target_roles = getattr(self, "_expanded_roles", None) or self.config.get("target_roles", [])
        if not target_roles:
            return jobs  # no roles configured → pass everything

        from job_finder.tools.scrapers._utils import _match_roles

        pre_count = len(jobs)
        filtered = [j for j in jobs if _match_roles(j.get("title", ""), target_roles)]
        dropped = pre_count - len(filtered)
        if dropped:
            logger.info("Role filter: removed %d/%d jobs not matching target roles", dropped, pre_count)
            if progress:
                progress(f"Role filter: removed {dropped} jobs not matching target roles")

        # Also purge existing DB records that don't match roles
        try:
            from job_finder.models.database import purge_non_matching_roles
            purged = purge_non_matching_roles(
                target_roles=target_roles,
                profile=self.profile_name,
            )
            if purged and progress:
                progress(f"Purged {purged} existing jobs not matching target roles")
        except Exception as e:
            logger.debug("DB role purge failed (non-fatal): %s", e)

        return filtered

    # -- Staffing agency filter -------------------------------------------

    # Common staffing / recruitment agencies (lowercase for matching)
    _STAFFING_AGENCIES: set[str] = {
        "robert half", "teksystems", "randstad", "insight global",
        "adecco", "kelly services", "manpowergroup", "hays", "kforce",
        "apex systems", "aston carter", "aerotek", "modis",
        "beacon hill staffing", "cybercoders", "dice staffing",
        "express employment", "jobot", "michael page", "page group",
        "phaidon international", "recruiting from scratch",
        "signature consultants", "staffing solutions enterprises",
        "talent acquisition concepts", "talentbridge",
    }

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
        if not company:
            return False
        company_lower = company.lower().strip()
        for agency in cls._STAFFING_AGENCIES:
            if agency in company_lower:
                return True
        return False

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
        """Score a single job using the LLM. Returns None if unavailable."""
        if not self.llm or not self.llm.is_configured:
            return None

        user_msg = JD_SCORER_USER_TEMPLATE.format(
            resume_text=resume_text,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            job_description=job.get("description", ""),
        )
        scorer_prompt = build_scorer_prompt(self.config)
        return self.llm.chat_json(scorer_prompt, user_msg)

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
                )

        ai_available = use_ai and self.llm and self.llm.is_configured

        if ai_available:
            settings = self.config.get("search_settings") or {}
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
        loc_prefs = self.config.get("location_preferences", {})
        pref_locations, pref_states, pref_cities, pref_places, remote_only, include_remote = _resolve_location_filter_preferences(
            self.config.get("locations", []),
            loc_prefs,
        )
        if not (pref_locations or pref_states or pref_cities or pref_places or remote_only or not include_remote):
            return jobs

        filtered = [
            job for job in jobs
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
            )
        ]
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
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_score_one, j): j for j in jobs}
            for future in as_completed(futures):
                try:
                    job, ai_score = future.result()
                except Exception as e:
                    logger.warning("AI scoring failed for a job: %s", e)
                    failed += 1
                    continue
                done += 1
                if ai_score:
                    # Check if AI corrected the work type
                    ai_wt = ai_score.get("work_type")
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
            resume_text=resume_text,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            job_description=job.get("description", ""),
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
            resume_text=resume_text,
            job_title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            job_description=job.get("description", ""),
        )
        cl_prompt = build_cover_letter_prompt(self.config)
        return self.llm.chat_json(cl_prompt, user_msg)

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

        # Use grounded template when we have web results, plain template otherwise
        if web_context:
            user_msg = COMPANY_RESEARCHER_GROUNDED_USER_TEMPLATE.format(
                company_name=company_name,
                job_title=job_title,
                web_context=web_context,
            )
        else:
            user_msg = COMPANY_RESEARCHER_USER_TEMPLATE.format(
                company_name=company_name,
                job_title=job_title,
            )

        cr_prompt = build_company_researcher_prompt(self.config)
        return self.llm.chat_json(cr_prompt, user_msg)

    # -- Stage 7: Auto-apply (opt-in) -------------------------------------

    def auto_apply_jobs(
        self,
        jobs: list[dict],
        resume_path: str = "",
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Auto-apply to qualifying jobs via detected ATS.

        Only applies to STRONG_APPLY jobs with Greenhouse or Lever URLs.
        Respects ``auto_apply`` config (enabled, dry_run, max_applications_per_run).
        """
        from job_finder.tools.auto_apply_tool import auto_apply

        apply_config = self.config.get("auto_apply", {})
        if not apply_config.get("enabled", False):
            if progress:
                progress("Auto-apply is disabled in config")
            return jobs

        dry_run = apply_config.get("dry_run", True)
        max_apps = apply_config.get("max_applications_per_run", 5)
        applied_count = 0

        candidates = [
            j for j in jobs
            if j.get("recommendation") == "STRONG_APPLY"
        ]

        if progress:
            mode = "DRY RUN" if dry_run else "LIVE"
            progress(f"Auto-apply ({mode}): {len(candidates)} STRONG_APPLY candidates")

        for job in candidates:
            if applied_count >= max_apps:
                break

            cover_letter = job.get("cover_letter", "")
            result = auto_apply(
                job=job,
                config=self.config,
                resume_path=resume_path,
                cover_letter_text=cover_letter,
                dry_run=dry_run,
            )

            method = result.get("method")
            if not method or method == "linkedin":
                continue

            if progress:
                action = "Would apply" if dry_run else "Applied"
                status = "OK" if result.get("success") else "FAILED"
                progress(
                    f"  {action} to {job.get('company', '')} via {method} [{status}]"
                )

            if result.get("success") and not dry_run:
                job["application_method"] = method
                applied_count += 1
                # Update DB record if we have an ID
                db_id = job.get("db_id")
                if db_id:
                    update_application_status(
                        db_id,
                        status="applied",
                        notes=f"Auto-applied via {method}",
                    )

        if progress:
            progress(f"Auto-apply complete: {applied_count} applications submitted")

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

        # 4. Enhance top jobs (AI only, when enhance=True)
        ai_available = use_ai and enhance and self.llm and self.llm.is_configured
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

                # Run all 3 LLM calls for this job in parallel
                tweaks = None
                cl = None
                intel = None

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

                with ThreadPoolExecutor(max_workers=3) as inner_pool:
                    inner_futures = [
                        inner_pool.submit(_get_tweaks),
                        inner_pool.submit(_get_cover_letter),
                        inner_pool.submit(_get_intel),
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

                return bool(tweaks or cl or intel)

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
                overall_score=job.get("overall_score"),
                technical_score=job.get("technical_score"),
                leadership_score=job.get("leadership_score"),
                comp_potential_score=job.get("comp_potential_score"),
                platform_building_score=job.get("platform_building_score"),
                company_trajectory_score=job.get("company_trajectory_score"),
                culture_fit_score=job.get("culture_fit_score"),
                career_progression_score=job.get("career_progression_score"),
                recommendation=job.get("recommendation"),
                score_reasoning=job.get("score_reasoning"),
                key_strengths=json.dumps(job.get("key_strengths", [])),
                key_gaps=json.dumps(job.get("key_gaps", [])),
                funding_stage=job.get("funding_stage"),
                total_funding=job.get("total_funding"),
                employee_count=job.get("employee_count"),
                company_intel_json=job.get("company_intel_json"),
                resume_tweaks_json=job.get("resume_tweaks_json"),
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

        # 6. Auto-apply (opt-in)
        apply_config = self.config.get("auto_apply", {})
        if apply_config.get("enabled", False):
            if progress:
                progress("Running auto-apply for top jobs...")
            resume_path = self.config.get("profile", {}).get("resume_path", "")
            if not resume_path:
                resume_path = find_resume(profile=self.profile_name) or ""
            self.auto_apply_jobs(jobs, resume_path=resume_path, progress=progress)

        if progress:
            progress(f"Done! Saved {saved} jobs ({enhanced_count} enhanced with AI)")

        return jobs
