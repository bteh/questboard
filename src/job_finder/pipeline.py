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
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from job_finder.tools.job_search_tool import search_jobs
from job_finder.tools.resume_parser_tool import find_resume, parse_resume

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def _load_search_config(profile: str | None = None) -> dict:
    """Load config for the given profile.

    Looks for ``config/profiles/{profile}.yaml`` first, then falls back
    to ``config/search_config.yaml`` for backward compatibility.
    """
    config_dir = os.path.join(os.path.dirname(__file__), "config")

    if profile and profile != "default":
        profile_path = os.path.join(config_dir, "profiles", f"{profile}.yaml")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        logger.warning("Profile '%s' not found, using default config", profile)

    # Fallback: original search_config.yaml
    config_path = os.path.join(config_dir, "search_config.yaml")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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


def _dedup_key(company: str, title: str) -> str:
    """Create a normalized key for fuzzy dedup on company + title."""
    return f"{_normalize_company(company)}||{_normalize_title(title)}"


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

# Short keywords that should never be merged away (industry-specific terms).
# Users can add their own domain terms in profile keyword_searches.
_TECH_KEYWORDS = {
    "dbt", "trino", "lakehouse", "iceberg", "spark", "airflow", "flink",
    "kafka", "snowflake", "databricks", "bigquery", "redshift", "pyspark",
}


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
) -> list[str]:
    """Reduce redundant JobSpy queries by grouping similar search terms.

    Strategy:
    1. Strip seniority and management prefixes to find the *base role*.
    2. Group terms sharing the same base role; keep both the base (broadest)
       and the highest-seniority variant so job boards match senior titles.
    3. Keep high-value niche terms that would not surface via the broad query
       (e.g. ``"founding engineer data"``).
    4. Dedup keywords against roles so the same base is not searched twice.
    5. Always keep short technology keywords (``"dbt"``, ``"Trino"``, etc.)
       as-is because they represent distinct intent.

    Returns the consolidated list and logs what was merged.
    """
    # Seniority tiers for picking the "highest" variant to keep
    _SENIORITY_RANK = {
        "principal": 5, "staff": 4, "head of": 4,
        "senior": 3, "lead": 3, "founding": 3,
        "junior": 1,
    }
    _MANAGEMENT_RANK = {
        "vp of": 5, "vp": 5,
        "director of": 4, "director": 4,
        "senior manager": 3, "manager": 2,
    }

    # --- Phase 1: group roles by base role ---
    base_groups: dict[str, list[tuple[str, int]]] = {}  # base_role -> [(original_term, rank)]

    for term in roles:
        t = term.strip()
        if not t:
            continue

        # Try stripping seniority first, then management
        pfx, base = _strip_prefix(t, _SENIORITY_PREFIXES)
        rank = _SENIORITY_RANK.get(pfx, 0)
        if not pfx:
            pfx, base = _strip_prefix(t, _MANAGEMENT_PREFIXES)
            rank = _MANAGEMENT_RANK.get(pfx, 0)

        # Normalize the base for grouping
        base_key = re.sub(r"\s+", " ", base.lower().strip())
        base_groups.setdefault(base_key, []).append((t, rank))

    # For each group: keep the base role (broadest) AND the highest-seniority
    # variant if it's different from the base.  This ensures job boards that
    # match on title keywords surface senior-level results too.
    consolidated: list[str] = []
    kept_bases: set[str] = set()

    for base_key, group in base_groups.items():
        if len(group) == 1:
            consolidated.append(group[0][0])
        else:
            # Always emit the base role for broad coverage
            consolidated.append(base_key)

            # Also keep the highest-seniority variant for targeted results
            best_term, best_rank = max(group, key=lambda x: x[1])
            if best_rank > 0 and best_term.lower().strip() != base_key:
                consolidated.append(best_term)
                logger.info(
                    "Consolidated %d terms for '%s': base + senior variant '%s' (merged away: %s)",
                    len(group), base_key, best_term,
                    [t for t, _ in group if t != best_term and t.lower().strip() != base_key],
                )
            else:
                logger.info(
                    "Consolidated %d search terms into '%s': merged %s",
                    len(group), base_key, [t for t, _ in group],
                )

        kept_bases.add(base_key)

    # --- Phase 2: process keywords ---
    for kw in keywords:
        kw_stripped = kw.strip()
        if not kw_stripped:
            continue

        kw_lower = kw_stripped.lower()

        # Always keep short technology keywords
        if kw_lower in _TECH_KEYWORDS or len(kw_lower) <= 4:
            if kw_stripped not in consolidated:
                consolidated.append(kw_stripped)
            continue

        # Check if this keyword's base overlaps with an existing role base
        _, kw_base = _strip_prefix(kw_stripped, _SENIORITY_PREFIXES)
        if not _:
            _, kw_base = _strip_prefix(kw_stripped, _MANAGEMENT_PREFIXES)
        kw_base_key = re.sub(r"\s+", " ", kw_base.lower().strip())

        if kw_base_key in kept_bases:
            logger.info(
                "Keyword '%s' overlaps with role base '%s' — skipping",
                kw_stripped, kw_base_key,
            )
            continue

        # Keep high-value niche terms regardless
        if _HIGH_VALUE_PATTERNS.search(kw_stripped):
            if kw_stripped not in consolidated:
                consolidated.append(kw_stripped)
                logger.info("Keeping high-value keyword: '%s'", kw_stripped)
            continue

        # Otherwise, add if not a duplicate
        if kw_stripped not in consolidated:
            consolidated.append(kw_stripped)
            kept_bases.add(kw_base_key)

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
            "indeed": 5, "linkedin": 4, "glassdoor": 3,
            "zip_recruiter": 2, "google": 1,
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
    """Remove duplicate jobs based on URL and fuzzy company+title matching.

    When the same job appears from multiple sources (e.g. Indeed, Glassdoor,
    Google Jobs), keeps the version with the richest data and merges salary
    info from siblings.  This runs BEFORE scoring so each unique job is
    scored exactly once, eliminating inconsistent scores for the same posting.
    """
    seen_urls: set[str] = set()
    groups: dict[str, list[dict]] = {}
    no_key: list[dict] = []

    for job in jobs:
        url = job.get("url", "")
        # Exact URL dedup (fast path)
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        company = job.get("company", "")
        title = job.get("title", "")
        if company and title:
            key = _dedup_key(company, title)
            groups.setdefault(key, []).append(job)
        else:
            no_key.append(job)

    unique: list[dict] = []
    for group in groups.values():
        unique.append(_pick_best_job(group) if len(group) > 1 else group[0])
    unique.extend(no_key)
    return unique


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
        roles_raw = roles or self.config.get("target_roles", [])
        locations = locations or self.config.get("locations", ["Los Angeles, CA"])
        settings = self.config.get("search_settings", {})
        results_per_board = settings.get("results_per_board", 25)
        results_per_additional = settings.get("results_per_additional_source", 100)
        max_days_old = settings.get("max_days_old", 14)

        # Consolidate similar search terms to reduce redundant JobSpy queries
        keywords_raw = self.config.get("keyword_searches", [])
        consolidated = _consolidate_search_terms(roles_raw, keywords_raw)

        # If consolidation reduced query count, increase results_per_board so
        # each broad query covers more ground.
        original_count = len(roles_raw) + len(keywords_raw)
        if consolidated and len(consolidated) < original_count:
            results_per_board = min(100, results_per_board * 2)
            logger.info(
                "Consolidated %d → %d search terms; bumped results_per_board to %d",
                original_count, len(consolidated), results_per_board,
            )

        # Build list of all JobSpy search tasks (consolidated term × location)
        search_tasks: list[tuple[str, str]] = []
        for term in consolidated:
            for loc in locations:
                search_tasks.append((term, loc))

        total_tasks = len(search_tasks)
        counter = {"done": 0}
        lock = threading.Lock()
        all_jobs: list[dict] = []

        def _search_one(task: tuple[str, str]) -> list[dict]:
            term, loc = task
            is_remote = True if loc.lower() == "remote" else None
            jobs = search_jobs(
                search_term=term,
                location=loc if loc.lower() != "remote" else "United States",
                results_wanted=results_per_board,
                hours_old=max_days_old * 24,
                is_remote=is_remote,
                country=settings.get("country", "USA"),
            )
            with lock:
                counter["done"] += 1
                n = counter["done"]
            if progress:
                sources = ", ".join(set(j.get("source", "?") for j in jobs)) if jobs else "no boards"
                progress(f"  [{n}/{total_tasks}] '{term}' in {loc} → {len(jobs)} results from {sources}")
            return jobs

        # --- Launch JobSpy searches + additional scrapers concurrently ---
        if progress:
            progress(f"Searching {total_tasks} role×location combos in parallel...")

        max_jobspy_workers = min(total_tasks, settings.get("max_parallel_searches", 4))

        # Prepare additional scraper arguments
        enabled_names: list[str] = []
        try:
            from job_finder.tools.scrapers import get_registry, run_scrapers

            extra_sources = self.config.get("additional_sources", [])
            all_scrapers = get_registry()

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

        # Run JobSpy searches in a thread pool, and additional scrapers
        # concurrently in their own thread.
        extra_jobs_result: list[dict] = []

        def _run_additional_scrapers() -> None:
            nonlocal extra_jobs_result
            try:
                from job_finder.tools.scrapers import run_scrapers
                extra_jobs_result = run_scrapers(
                    names=enabled_names,
                    roles=roles_raw,
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
                futures = [pool.submit(_search_one, t) for t in search_tasks]
                for future in as_completed(futures):
                    try:
                        all_jobs.extend(future.result())
                    except Exception as e:
                        logger.warning("JobSpy search failed (non-fatal): %s", e)

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
        if loc_prefs.get("filter_enabled", False):
            pref_states = loc_prefs.get("preferred_states", [])
            pref_cities = loc_prefs.get("preferred_cities", [])
            remote_only = loc_prefs.get("remote_only", False)
        else:
            # Auto-derive from search locations (e.g. "Los Angeles, CA" → state=CA, city=Los Angeles)
            from job_finder.company_classifier import parse_location as _parse_loc
            pref_states = []
            pref_cities = []
            remote_only = False
            for loc in locations:
                if loc.lower() in ("remote", "united states", "usa", "us", "anywhere"):
                    continue
                parsed = _parse_loc(loc)
                if parsed["state"] and parsed["state"] not in pref_states:
                    pref_states.append(parsed["state"])
                if parsed["city"] and parsed["city"] not in pref_cities:
                    pref_cities.append(parsed["city"])

        if pref_states or pref_cities or remote_only:
            pre_count = len(deduped)
            deduped = [
                j for j in deduped
                if location_matches_preferences(
                    j.get("location", ""),
                    j.get("is_remote", False),
                    preferred_states=pref_states,
                    preferred_cities=pref_cities,
                    remote_only=remote_only,
                    work_type=j.get("work_type", ""),
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
                    profile=self.profile_name,
                )
                if purged and progress:
                    progress(f"Purged {purged} existing jobs outside preferred locations")
            except Exception as e:
                logger.debug("DB location purge failed (non-fatal): %s", e)

        return deduped

    # -- Stage 2: Resume parsing (no LLM) ---------------------------------

    def get_resume_text(self, path: str = "") -> str:
        """Return the full text of the candidate's resume."""
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
        """Score all jobs with a two-pass approach for speed.

        Pass 1: Basic keyword scoring for ALL jobs (fast, no LLM).
        Pass 2: AI scoring for top candidates only (when use_ai=True).

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

        # Pass 0.5: LLM company intel for known companies (parallel, cached)
        # Uses AI knowledge of Levels.fyi / Blind / Glassdoor data to get
        # per-company baselines instead of coarse tier defaults.
        company_intel_cache: dict[str, dict[str, float]] = {}
        ai_intel = use_ai and self.llm and self.llm.is_configured
        if ai_intel:
            # Deduplicate by normalized name so "Stripe, Inc." and "stripe" → one call
            seen_keys: dict[str, tuple[str, str, str]] = {}
            for job in jobs:
                ct = job.get("company_type", "Unknown")
                if ct == "Unknown":
                    continue
                raw = job.get("company", "")
                key = normalize_company_key(raw)
                if not key or key in seen_keys:
                    continue
                context_parts = []
                if job.get("funding_stage"):
                    context_parts.append(f"Funding: {job['funding_stage']}")
                if job.get("employee_count"):
                    context_parts.append(f"Employees: {job['employee_count']}")
                seen_keys[key] = (raw, ct, ", ".join(context_parts))

            if seen_keys and progress:
                progress(f"Getting AI company intel for {len(seen_keys)} known companies...")

            def _fetch_intel(args: tuple[str, str, str]) -> tuple[str, dict[str, float] | None]:
                name, ct, ctx = args
                return normalize_company_key(name), get_company_baselines(
                    self.llm, name, ct, context=ctx,
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                for key, baselines in pool.map(_fetch_intel, seen_keys.values()):
                    if key and baselines:
                        company_intel_cache[key] = baselines

        # Pass 1: Fast keyword scoring for all jobs
        if progress:
            progress(f"Quick-scoring {len(jobs)} jobs against resume keywords...")
        for i, job in enumerate(jobs, 1):
            # Use LLM company baselines if available, else fall back to tier
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
                is_remote=job.get("is_remote", False),
                config=self.config,
                company_baselines=co_baselines,
            )
            job.update(score_data)
            # Log progress every 100 jobs to avoid spam
            if progress and (i % 100 == 0 or i == len(jobs)):
                progress(f"  Quick-scored {i}/{len(jobs)} jobs")

        # Sort by basic score
        jobs.sort(key=lambda j: j.get("overall_score", 0), reverse=True)

        # Summary after basic pass
        above_40 = sum(1 for j in jobs if (j.get("overall_score") or 0) >= 40)
        above_55 = sum(1 for j in jobs if (j.get("overall_score") or 0) >= 55)
        if progress:
            progress(f"Quick-score done: {above_55} strong matches, {above_40} worth reviewing, {len(jobs) - above_40} filtered out")

        # Pass 2: AI scoring for top candidates only (parallel)
        ai_available = use_ai and self.llm and self.llm.is_configured
        if ai_available:
            # Only AI-score jobs with basic score >= 50, cap at 25
            ai_threshold = self.config.get("scoring", {}).get("ai_threshold", 50)
            ai_candidates = [j for j in jobs if (j.get("overall_score") or 0) >= ai_threshold][:25]
            if ai_candidates:
                if progress:
                    progress(f"AI-scoring top {len(ai_candidates)} jobs in parallel (skipping {len(jobs) - len(ai_candidates)} low-relevance)...")

                def _score_one(job: dict) -> tuple[dict, dict | None]:
                    return job, self.score_job_with_ai(job, resume_text)

                done = 0
                work_type_corrections = 0
                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = {pool.submit(_score_one, j): j for j in ai_candidates}
                    for future in as_completed(futures):
                        job, ai_score = future.result()
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
                        if progress and (done % 5 == 0 or done == len(ai_candidates)):
                            progress(f"  AI-scored {done}/{len(ai_candidates)} jobs")

                if work_type_corrections and progress:
                    progress(f"  AI corrected work type for {work_type_corrections} jobs")

                # Re-sort after AI scoring
                jobs.sort(key=lambda j: j.get("overall_score", 0), reverse=True)
            elif progress:
                progress("No jobs scored high enough for AI analysis")

        return jobs

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
        if progress:
            progress("Searching job boards...")
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
