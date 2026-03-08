"""Job-search pipeline — framework-free orchestration.

Replaces the CrewAI crew with a simple Python pipeline.
LLM features are *optional*: search, track and basic scoring work with
zero LLM configuration.
"""

from __future__ import annotations

import json
import logging
import os
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
    location_matches_preferences,
)
from job_finder.scorer import score_job_basic
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


def _deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs based on URL."""
    seen: set[str] = set()
    unique: list[dict] = []
    for job in jobs:
        url = job.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        unique.append(job)
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
        """Scrape job boards for every role x location combination.

        Returns a deduplicated list of job dicts.
        """
        roles = roles or self.config.get("target_roles", [])
        locations = locations or self.config.get("locations", ["Los Angeles, CA"])
        settings = self.config.get("search_settings", {})
        results_per_board = settings.get("results_per_board", 25)
        max_days_old = settings.get("max_days_old", 14)

        all_jobs: list[dict] = []
        total = len(roles) * len(locations)
        idx = 0

        for role in roles:
            for loc in locations:
                idx += 1
                if progress:
                    progress(f"Searching '{role}' in {loc}  ({idx}/{total})")

                is_remote = True if loc.lower() == "remote" else None
                jobs = search_jobs(
                    search_term=role,
                    location=loc if loc.lower() != "remote" else "United States",
                    results_wanted=results_per_board,
                    hours_old=max_days_old * 24,
                    is_remote=is_remote,
                    country=settings.get("country", "USA"),
                )
                all_jobs.extend(jobs)

        # Also run keyword searches
        for kw in self.config.get("keyword_searches", []):
            for loc in locations:
                idx += 1
                if progress:
                    progress(f"Searching keyword '{kw}' in {loc}")

                is_remote = True if loc.lower() == "remote" else None
                jobs = search_jobs(
                    search_term=kw,
                    location=loc if loc.lower() != "remote" else "United States",
                    results_wanted=results_per_board,
                    hours_old=max_days_old * 24,
                    is_remote=is_remote,
                    country=settings.get("country", "USA"),
                )
                all_jobs.extend(jobs)

        # Search YC Work at a Startup (if enabled)
        yc_enabled = any(
            s.get("name") == "workatastartup" and s.get("enabled")
            for s in self.config.get("additional_sources", [])
        )
        if yc_enabled:
            if progress:
                progress("Searching YC Work at a Startup...")
            try:
                from job_finder.tools.yc_scraper_tool import search_yc_jobs

                yc_jobs = search_yc_jobs(
                    roles=roles,
                    max_results=results_per_board,
                )
                all_jobs.extend(yc_jobs)
                if progress:
                    progress(f"  Found {len(yc_jobs)} jobs from YC startups")
            except Exception as e:
                logger.warning("YC scraper failed (non-fatal): %s", e)
                if progress:
                    progress(f"  YC scraper unavailable: {e}")

        # Search additional sources (Remotive, Himalayas, WWR, HN, Greenhouse, Lever)
        extra_sources = self.config.get("additional_sources", [])
        enabled_extras = [
            s["name"] for s in extra_sources
            if s.get("enabled") and s["name"] not in ("workatastartup", "greenhouse", "lever")
        ]
        # Always-on lightweight sources when any additional sources are configured
        if enabled_extras:
            try:
                from job_finder.tools.additional_scrapers import search_additional_sources

                extra_jobs = search_additional_sources(
                    roles=roles,
                    max_results_per_source=results_per_board,
                    sources=enabled_extras,
                    progress=progress,
                )
                all_jobs.extend(extra_jobs)
            except Exception as e:
                logger.warning("Additional scrapers failed (non-fatal): %s", e)
                if progress:
                    progress(f"  Additional scrapers error: {e}")

        deduped = _deduplicate(all_jobs)
        if progress:
            progress(f"Found {len(deduped)} unique jobs (from {len(all_jobs)} raw)")
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
        """Score all jobs — AI when available, basic otherwise.

        Each job dict is *mutated* to include score fields.
        """
        for i, job in enumerate(jobs, 1):
            if progress:
                progress(f"Scoring job {i}/{len(jobs)}: {job.get('title', '')} @ {job.get('company', '')}")

            score_data: dict | None = None
            if use_ai and self.llm and self.llm.is_configured:
                score_data = self.score_job_with_ai(job, resume_text)

            if score_data is None:
                score_data = score_job_basic(
                    job_description=job.get("description", ""),
                    resume_text=resume_text,
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                    salary_min=job.get("salary_min"),
                    salary_max=job.get("salary_max"),
                    is_remote=job.get("is_remote", False),
                    config=self.config,
                )

            job.update(score_data)

        # Sort descending by score
        jobs.sort(key=lambda j: j.get("overall_score", 0), reverse=True)
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

    def research_company(self, company_name: str, job_title: str = "") -> dict | None:
        """Build a company intelligence profile. Returns None without LLM."""
        if not self.llm or not self.llm.is_configured:
            return None

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

        # 1b. Post-search location filter
        loc_prefs = self.config.get("location_preferences", {})
        if loc_prefs.get("filter_enabled", False):
            pref_states = loc_prefs.get("preferred_states", [])
            pref_cities = loc_prefs.get("preferred_cities", [])
            if pref_states or pref_cities:
                pre_count = len(jobs)
                jobs = [
                    j for j in jobs
                    if location_matches_preferences(
                        j.get("location", ""),
                        j.get("is_remote", False),
                        preferred_states=pref_states,
                        preferred_cities=pref_cities,
                    )
                ]
                if progress:
                    progress(f"Location filter: {pre_count} -> {len(jobs)} jobs (kept {len(jobs)})")

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

        # 4. Enhance top jobs (AI only)
        ai_available = use_ai and self.llm and self.llm.is_configured
        strong = [j for j in jobs if j.get("recommendation") in ("STRONG_APPLY", "APPLY")]
        enhanced_count = 0

        if ai_available and has_resume and strong:
            if progress:
                progress(f"Enhancing top {len(strong)} jobs with AI...")
            for i, job in enumerate(strong, 1):
                if progress:
                    progress(f"  Enhancing {i}/{len(strong)}: {job.get('company', '')}")

                # Resume tweaks (STRONG_APPLY and APPLY)
                tweaks = self.optimize_resume(job, resume_text)
                if tweaks:
                    job["resume_tweaks_json"] = json.dumps(tweaks)

                # Cover letter (STRONG_APPLY only)
                cl = None
                if job.get("recommendation") == "STRONG_APPLY":
                    cl = self.write_cover_letter(job, resume_text)
                    if cl:
                        job["cover_letter"] = cl.get("cover_letter_text", "")

                # Company research
                intel = self.research_company(
                    job.get("company", ""), job.get("title", "")
                )
                if intel:
                    job["company_intel_json"] = json.dumps(intel)
                    job["funding_stage"] = intel.get("funding_stage", "")
                    job["total_funding"] = intel.get("total_funding", "")
                    job["employee_count"] = intel.get("employee_count", "")

                if tweaks or cl or intel:
                    enhanced_count += 1

        # 5. Save to database
        if progress:
            progress("Saving results to database...")
        saved = 0
        for job in jobs:
            # Classify company type
            ct = classify_company(
                job.get("company", ""),
                job.get("funding_stage"),
                job.get("total_funding"),
                job.get("employee_count"),
            )
            job["company_type"] = ct

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
