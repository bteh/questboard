"""Pydantic models for structured pipeline outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    FOUND = "found"
    REVIEWED = "reviewed"
    APPLYING = "applying"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class JobListing(BaseModel):
    """A single job listing scraped from a job board."""

    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: str = Field(description="Job location (city or Remote)")
    url: str = Field(description="URL to the job posting")
    source: str = Field(description="Job board source (LinkedIn, Indeed, etc.)")
    description: str = Field(default="", description="Full job description text")
    salary_min: Optional[float] = Field(default=None, description="Minimum salary if listed")
    salary_max: Optional[float] = Field(default=None, description="Maximum salary if listed")
    date_posted: Optional[str] = Field(default=None, description="Date the job was posted")
    is_remote: bool = Field(default=False, description="Whether the role is remote")
    company_size: Optional[str] = Field(default=None, description="Company size if available")
    scraped_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when scraped",
    )


class SearchResults(BaseModel):
    """Aggregated search results from all job boards."""

    jobs: list[JobListing] = Field(default_factory=list, description="List of job listings")
    total_found: int = Field(default=0, description="Total number of jobs found")
    search_queries: list[str] = Field(
        default_factory=list, description="Queries that were executed"
    )
    boards_searched: list[str] = Field(
        default_factory=list, description="Job boards that were searched"
    )
    searched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of the search",
    )


class SkillMatch(BaseModel):
    """Individual skill match detail."""

    skill: str = Field(description="Skill or technology name")
    required: bool = Field(description="Whether it's listed as required vs nice-to-have")
    candidate_has: bool = Field(description="Whether the candidate has this skill")
    evidence: str = Field(default="", description="Evidence from resume supporting the match")


class JobScore(BaseModel):
    """Scoring result for a job listing against the candidate's resume."""

    job_title: str = Field(description="Job title being scored")
    company: str = Field(description="Company name")
    job_url: str = Field(description="URL to the posting")
    overall_score: float = Field(
        description="Overall fit score from 0-100", ge=0, le=100
    )
    technical_score: float = Field(
        description="Technical skills match 0-100", ge=0, le=100
    )
    leadership_score: float = Field(
        description="Leadership/seniority alignment 0-100", ge=0, le=100
    )
    platform_building_score: float = Field(
        description="Signal that this is a 'build from scratch' role 0-100", ge=0, le=100
    )
    comp_potential_score: float = Field(
        description="Likelihood of hitting $300K+ total comp 0-100", ge=0, le=100
    )
    company_trajectory_score: float = Field(
        description="Company growth/funding trajectory 0-100", ge=0, le=100
    )
    culture_fit_score: float = Field(
        description="Culture and work style fit 0-100", ge=0, le=100
    )
    career_progression_score: float = Field(
        description="Career progression/upgrade signal 0-100", ge=0, le=100
    )
    skill_matches: list[SkillMatch] = Field(
        default_factory=list, description="Detailed skill-by-skill matching"
    )
    key_strengths: list[str] = Field(
        default_factory=list,
        description="Top reasons this is a good fit",
    )
    key_gaps: list[str] = Field(
        default_factory=list,
        description="Areas where candidate doesn't match JD",
    )
    recommendation: str = Field(
        description="STRONG_APPLY, APPLY, MAYBE, or SKIP"
    )
    reasoning: str = Field(
        description="2-3 sentence explanation of the score and recommendation"
    )


class BulletTweak(BaseModel):
    """A suggested resume bullet point modification."""

    original_bullet: str = Field(description="The original resume bullet point")
    tweaked_bullet: str = Field(description="The optimized version for this role")
    rationale: str = Field(description="Why this change improves the match")
    target_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords from the JD this bullet now addresses",
    )


class ResumeOptimization(BaseModel):
    """Resume optimization suggestions tailored to a specific role."""

    job_title: str = Field(description="Target job title")
    company: str = Field(description="Target company")
    bullet_tweaks: list[BulletTweak] = Field(
        default_factory=list,
        description="Suggested bullet point modifications",
    )
    keywords_to_add: list[str] = Field(
        default_factory=list,
        description="Keywords from JD missing from resume that should be woven in",
    )
    sections_to_emphasize: list[str] = Field(
        default_factory=list,
        description="Resume sections to move up or expand",
    )
    title_suggestion: str = Field(
        default="",
        description="Suggested resume headline/title for this application",
    )
    summary_rewrite: str = Field(
        default="",
        description="Rewritten professional summary tailored to this role",
    )
    ats_compatibility_notes: list[str] = Field(
        default_factory=list,
        description="ATS optimization tips specific to this application",
    )


class CoverLetter(BaseModel):
    """A tailored cover letter for a specific role."""

    job_title: str = Field(description="Target job title")
    company: str = Field(description="Target company")
    cover_letter_text: str = Field(description="The full cover letter text")
    key_hooks: list[str] = Field(
        default_factory=list,
        description="Key talking points woven into the letter",
    )
    company_specific_references: list[str] = Field(
        default_factory=list,
        description="Company-specific details referenced in the letter",
    )
    tone: str = Field(
        default="confident-technical",
        description="Tone of the letter (e.g., confident-technical, visionary-leader)",
    )


class RequirementMatch(BaseModel):
    """A single JD requirement mapped against the candidate's resume.

    This is the "show your work" piece of the evaluation report: instead of
    giving the user a single numeric score, we walk through each requirement
    the job description asks for and show exactly how (or whether) the
    candidate's resume backs it up. The `evidence` field should be a direct
    quote from the resume — not a paraphrase — so the user can verify the
    reasoning with their own eyes.

    Inspired by the requirement-to-line mapping in career-ops's Block B.
    """

    requirement: str = Field(
        description="The specific requirement pulled from the job description",
    )
    strength: str = Field(
        description="strong (clearly demonstrated), partial (some evidence), missing (no evidence in resume)",
    )
    evidence: str = Field(
        default="",
        description="Exact quote from the candidate's resume that demonstrates this requirement. Empty if strength is 'missing'.",
    )
    mitigation: str = Field(
        default="",
        description="How to address this gap if strength is 'missing' or 'partial' (e.g., 'lean on your Docker experience and mention K8s certification in progress')",
    )


class EvaluationReport(BaseModel):
    """Structured, interview-prep-ready evaluation of a job against the candidate.

    Sibling to the 0-100 numeric JobScore. Where JobScore sorts jobs, this
    report is the artifact a human actually reads before deciding whether to
    apply — archetype, TL;DR, requirement-by-requirement match with exact
    resume-line citations, gaps, recommended positioning, red flags.
    """

    archetype: str = Field(
        default="",
        description="Short human label for the role shape (e.g., 'AI Platform Engineer', 'Staff Frontend', 'ICU Nurse'). Helps the user recognize the role at a glance.",
    )
    tldr: str = Field(
        default="",
        description="One-sentence summary of what this role actually is and why it does or doesn't fit the candidate.",
    )
    requirements: list[RequirementMatch] = Field(
        default_factory=list,
        description="Each JD requirement mapped against the candidate's resume with exact-quote evidence.",
    )
    top_gaps: list[str] = Field(
        default_factory=list,
        description="The 3-5 most important gaps the candidate should be ready to explain or mitigate.",
    )
    recommended_framing: str = Field(
        default="",
        description="How the candidate should position themselves for this specific role — a 2-3 sentence narrative hook.",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Concerns about the role, company, or compensation worth raising before applying.",
    )


class GeneratedProfileScoring(BaseModel):
    """The 7 weighted scoring dimensions, must sum to 1.0 (within 0.01)."""

    technical_skills: float = Field(ge=0.0, le=1.0)
    leadership_signal: float = Field(ge=0.0, le=1.0)
    career_progression: float = Field(ge=0.0, le=1.0)
    platform_building: float = Field(ge=0.0, le=1.0)
    comp_potential: float = Field(ge=0.0, le=1.0)
    company_trajectory: float = Field(ge=0.0, le=1.0)
    culture_fit: float = Field(ge=0.0, le=1.0)


class GeneratedProfileKeywords(BaseModel):
    """Three keyword buckets fed into the scoring pipeline."""

    technical: list[str] = Field(
        default_factory=list,
        description="5–15 specific technical / domain keywords from the resume.",
    )
    leadership: list[str] = Field(
        default_factory=list,
        description="3–8 leadership / seniority signals (titles or behaviors).",
    )
    signal_terms: list[str] = Field(
        default_factory=list,
        description="3–8 phrases that mean 'this is a good fit' for this person specifically.",
    )


class GeneratedProfileCompensation(BaseModel):
    """Compensation targets inferred from the resume's seniority + domain."""

    currency: str = Field(default="USD")
    pay_period: str = Field(default="annual")
    min_base: int = Field(ge=0)
    target_total_comp: int = Field(ge=0)
    include_equity: bool = Field(default=False)


class GeneratedProfile(BaseModel):
    """LLM-tailored search profile generated from a candidate's resume.

    The schema deliberately mirrors the YAML archetype shape so the same
    `apply_archetype()` merge logic in src/job_finder/profiles/archetypes.py
    can consume either source. The frontend treats this object as
    interchangeable with a hardcoded template — the only difference is the
    `archetype.confidence` and `archetype.reasoning` fields, which expose
    the LLM's introspection.

    The whole point is to make Launchboard work for *any* career, not
    just the seven hardcoded buckets. A user with an unusual or
    multi-domain background gets a profile generated specifically for
    them, rather than being forced into the closest preset.
    """

    detected_archetype: str = Field(
        description="Short human-readable label for what kind of role this person wants next, e.g., 'AI Research Engineer at frontier labs', 'Pediatric ICU Nurse, Acute Care', 'Founding Engineer at a Web3 startup'. NOT one of the hardcoded slugs — this is the LLM's specific classification.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="LLM's confidence (0.0–1.0) in the detected archetype. Below 0.5 = the resume was sparse or atypical and the user should manually pick a template.",
    )
    reasoning: str = Field(
        description="2–3 sentences explaining why this archetype was chosen. Surfaced in the UI so the user can sanity-check the LLM.",
    )
    closest_template: str | None = Field(
        default=None,
        description="If one of our hardcoded archetype slugs is a reasonable fit, surface it here so the UI can offer 'use this template instead'. Null if no template is close.",
    )
    career_target: str = Field(
        description="One sentence: what role this person wants next. Drives the search query language.",
    )
    seniority_signal: str = Field(
        description="Inferred seniority: entry / mid / senior / staff / principal / exec.",
    )
    scoring: GeneratedProfileScoring
    keywords: GeneratedProfileKeywords
    target_roles: list[str] = Field(
        default_factory=list,
        description="3–6 example role titles to seed the wizard's target-role input.",
    )
    compensation: GeneratedProfileCompensation
    enabled_scrapers: list[str] = Field(
        default_factory=list,
        description="Subset of available scraper names that make sense for this person. Must be a subset of the available_scrapers list passed in the prompt.",
    )
    recommended_external_boards: list[str] = Field(
        default_factory=list,
        description="URLs of niche job boards Launchboard does NOT yet scrape but that this candidate should manually check. Lets the system surface domain-specific boards (aijobs.ai for AI, web3.career for crypto, USAJobs.gov for government, etc.) without us needing a scraper for every one.",
    )
    primary_strengths: list[str] = Field(
        default_factory=list,
        description="3–5 things the LLM identified as this candidate's strongest selling points.",
    )
    development_areas: list[str] = Field(
        default_factory=list,
        description="2–3 areas where the candidate's resume is thin and should be addressed in cover letters or interview prep.",
    )


class CompanyIntel(BaseModel):
    """Intelligence gathered about a company."""

    company_name: str = Field(description="Company name")
    industry: str = Field(default="", description="Primary industry")
    funding_stage: Optional[str] = Field(
        default=None, description="Latest funding round (e.g., Series B)"
    )
    total_funding: Optional[str] = Field(
        default=None, description="Total funding raised"
    )
    employee_count: Optional[str] = Field(default=None, description="Approximate headcount")
    data_team_size: Optional[str] = Field(
        default=None, description="Estimated data team size"
    )
    tech_stack_signals: list[str] = Field(
        default_factory=list,
        description="Known technologies from job posts, GitHub, blog posts",
    )
    recent_news: list[str] = Field(
        default_factory=list, description="Recent company news/developments"
    )
    glassdoor_rating: Optional[float] = Field(
        default=None, description="Glassdoor rating if available"
    )
    growth_signals: list[str] = Field(
        default_factory=list,
        description="Signals of company growth (hiring pace, revenue, etc.)",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Any concerns (layoffs, bad reviews, runway issues)",
    )
    comp_intel: str = Field(
        default="",
        description="Compensation intelligence from Levels.fyi, Glassdoor, Blind",
    )
    why_join: str = Field(
        default="",
        description="Compelling reasons to join this company for this role",
    )
    interview_tips: list[str] = Field(
        default_factory=list,
        description="Tips for interviewing at this company",
    )
