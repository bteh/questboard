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
from job_finder.models.database import init_db, save_application
from job_finder.prompts import (
    COMPANY_RESEARCHER_SYSTEM_PROMPT,
    COMPANY_RESEARCHER_USER_TEMPLATE,
    COVER_LETTER_SYSTEM_PROMPT,
    COVER_LETTER_USER_TEMPLATE,
    JD_SCORER_SYSTEM_PROMPT,
    JD_SCORER_USER_TEMPLATE,
    RESUME_OPTIMIZER_SYSTEM_PROMPT,
    RESUME_OPTIMIZER_USER_TEMPLATE,
)
from job_finder.scorer import score_job_basic
from job_finder.tools.job_search_tool import search_jobs
from job_finder.tools.resume_parser_tool import parse_resume

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


def _load_search_config() -> dict:
    """Load ``search_config.yaml`` and return as dict."""
    config_path = os.path.join(
        os.path.dirname(__file__), "config", "search_config.yaml"
    )
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r") as f:
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

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm
        self.config = _load_search_config()

    # -- Stage 1: Search (no LLM) -----------------------------------------

    def search_all_jobs(
        self,
        roles: list[str] | None = None,
        locations: list[str] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> list[dict]:
        """Scrape job boards for every role × location combination.

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
                )
                all_jobs.extend(jobs)

        deduped = _deduplicate(all_jobs)
        if progress:
            progress(f"Found {len(deduped)} unique jobs (from {len(all_jobs)} raw)")
        return deduped

    # -- Stage 2: Resume parsing (no LLM) ---------------------------------

    @staticmethod
    def get_resume_text(path: str = "") -> str:
        """Return the full text of the candidate's resume."""
        return parse_resume(path)

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
        return self.llm.chat_json(JD_SCORER_SYSTEM_PROMPT, user_msg)

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
        return self.llm.chat_json(RESUME_OPTIMIZER_SYSTEM_PROMPT, user_msg)

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
        return self.llm.chat_json(COVER_LETTER_SYSTEM_PROMPT, user_msg)

    # -- Stage 6: Company research (LLM only) -----------------------------

    def research_company(self, company_name: str, job_title: str = "") -> dict | None:
        """Build a company intelligence profile. Returns None without LLM."""
        if not self.llm or not self.llm.is_configured:
            return None

        user_msg = COMPANY_RESEARCHER_USER_TEMPLATE.format(
            company_name=company_name,
            job_title=job_title,
        )
        return self.llm.chat_json(COMPANY_RESEARCHER_SYSTEM_PROMPT, user_msg)

    # -- Full pipeline -----------------------------------------------------

    def run_full_pipeline(
        self,
        progress: Callable[[str], None] | None = None,
        roles: list[str] | None = None,
        locations: list[str] | None = None,
        use_ai: bool = True,
    ) -> list[dict]:
        """Execute the complete pipeline: search → score → enhance → save.

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
            progress("🔍 Searching job boards…")
        jobs = self.search_all_jobs(roles=roles, locations=locations, progress=progress)
        if not jobs:
            if progress:
                progress("No jobs found. Try broadening your search criteria.")
            return []

        # 2. Parse resume
        if progress:
            progress("📄 Parsing resume…")
        resume_text = self.get_resume_text()
        has_resume = not resume_text.startswith("ERROR")

        # 3. Score
        if has_resume:
            if progress:
                progress("📊 Scoring jobs against resume…")
            jobs = self.score_jobs(jobs, resume_text, use_ai=use_ai, progress=progress)
        else:
            if progress:
                progress("⚠️ No resume found — skipping scoring")

        # 4. Enhance top jobs (AI only)
        ai_available = use_ai and self.llm and self.llm.is_configured
        strong = [j for j in jobs if j.get("recommendation") in ("STRONG_APPLY", "APPLY")]

        if ai_available and has_resume and strong:
            if progress:
                progress(f"✨ Enhancing top {len(strong)} jobs with AI…")
            for i, job in enumerate(strong, 1):
                if progress:
                    progress(f"  Enhancing {i}/{len(strong)}: {job.get('company', '')}")

                # Resume tweaks (STRONG_APPLY and APPLY)
                tweaks = self.optimize_resume(job, resume_text)
                if tweaks:
                    job["resume_tweaks_json"] = json.dumps(tweaks)

                # Cover letter (STRONG_APPLY only)
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

        # 5. Save to database
        if progress:
            progress("💾 Saving results to database…")
        saved = 0
        for job in jobs:
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
            )
            if rec:
                saved += 1

        if progress:
            progress(f"✅ Done! Saved {saved} jobs ({len(strong)} enhanced with AI)")

        return jobs
