"""Keyword / TF-IDF based job scorer — works without any LLM.

Provides a baseline score by comparing resume text against a job description
using cosine similarity and domain-specific keyword checks.
"""

from __future__ import annotations

import math
import re
from typing import Any


# -- Keyword lists --------------------------------------------------------

TECHNICAL_KEYWORDS = [
    "dbt", "trino", "spark", "airflow", "python", "sql", "data modeling",
    "lakehouse", "iceberg", "snowflake", "databricks", "bigquery", "redshift",
    "kafka", "flink", "kubernetes", "docker", "terraform", "aws", "gcp",
    "azure", "postgresql", "etl", "elt", "data pipeline", "data warehouse",
    "data lake", "ci/cd", "git", "pandas", "pyspark",
]

LEADERSHIP_KEYWORDS = [
    "manager", "head of", "director", "lead", "principal", "staff",
    "founding", "architect", "vp of", "build the team", "hire and mentor",
    "own the roadmap", "team lead", "people management",
    "cto", "vp engineering", "director of engineering", "engineering manager",
]

PLATFORM_BUILDING_KEYWORDS = [
    "greenfield", "from scratch", "v1", "0 to 1", "zero to one",
    "build the foundation", "establish best practices", "new data platform",
    "founding engineer", "first data hire", "build out",
]

HIGH_COMP_SIGNALS = [
    "netflix", "nvidia", "airbnb", "stripe", "databricks", "snowflake",
    "confluent", "meta", "google", "apple", "amazon", "microsoft",
    "staff", "principal", "senior staff", "l6", "l7", "e6", "e7",
    "cto", "vp", "director",
]


# -- Career progression ---------------------------------------------------

_LEVEL_MAP = {
    "intern": 0, "junior": 1, "associate": 1,
    "mid": 2, "senior": 3, "sr": 3,
    "staff": 4, "principal": 5, "distinguished": 6,
    "tech lead": 3.5, "lead": 3.5,
    "manager": 4, "engineering manager": 4,
    "senior manager": 5, "senior engineering manager": 5,
    "director": 6, "senior director": 7,
    "vp": 8, "svp": 9, "cto": 10,
    "head of": 6, "founding": 4,
}

_SCOPE_KEYWORDS = [
    "build the team", "own the roadmap", "founding", "head of",
    "from scratch", "0 to 1", "define strategy", "budget", "p&l",
    "cross-functional", "org design", "build out the team",
]

_MGMT_SIGNALS = ["manager", "director", "vp", "cto", "head of"]


def _extract_level(title: str) -> float:
    """Extract a numeric level from a job title.

    Uses word-boundary matching to avoid false positives like
    'cto' matching inside 'director'.
    """
    title_lower = title.lower()
    matched_levels: list[float] = []
    for keyword, level in _LEVEL_MAP.items():
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, title_lower):
            matched_levels.append(level)
    if not matched_levels:
        return 2.0  # default to mid-level for unknown titles
    return max(matched_levels)


def _career_progression_score(
    job_title: str,
    job_description: str,
    salary_min: float | None,
    salary_max: float | None,
    config: dict,
) -> float:
    """Score whether this job represents a career upgrade (0-100).

    Signals: title escalation, scope expansion, comp increase,
    management track transition.
    """
    baseline = config.get("career_baseline", {})
    current_level = _extract_level(
        baseline.get("current_title", "senior data engineer")
    )
    current_tc = baseline.get("current_tc", 200_000)

    job_level = _extract_level(job_title)

    score = 50.0  # neutral starting point

    # Title escalation component (up to +30 / down to -40)
    level_diff = job_level - current_level
    if level_diff > 0:
        score += min(level_diff * 15, 30)
    elif level_diff < 0:
        score += max(level_diff * 20, -40)

    # Scope expansion signals (up to +20)
    combined = f"{job_title} {job_description}".lower()
    scope_matches = sum(1 for kw in _SCOPE_KEYWORDS if kw in combined)
    score += min(scope_matches * 5, 20)

    # Compensation upgrade component (up to +20 / down to -15)
    if salary_max and salary_max > 0:
        if salary_max > current_tc * 1.3:
            score += 20
        elif salary_max > current_tc * 1.1:
            score += 10
        elif salary_max < current_tc * 0.85:
            score -= 15

    # Management track bonus for IC→manager transition
    title_lower = job_title.lower()
    is_mgmt_role = any(
        re.search(r'\b' + re.escape(sig) + r'\b', title_lower)
        for sig in _MGMT_SIGNALS
    )
    if is_mgmt_role and current_level <= 4:  # current is staff or below
        score += 10

    return max(0.0, min(score, 100.0))


# -- Scoring helpers ------------------------------------------------------

def _keyword_count(text: str, keywords: list[str]) -> int:
    """Return the number of keywords found in text (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def _keyword_score(text: str, keywords: list[str], saturation: int = 5) -> float:
    """Score keyword matches on a 0-100 scale with diminishing returns.

    Uses a saturation curve: finding `saturation` keywords gives ~80/100.
    This avoids penalising jobs for not matching ALL keywords.
    """
    count = _keyword_count(text, keywords)
    if count == 0:
        return 0.0
    # Asymptotic curve: score = 100 * (1 - e^(-count/saturation_factor))
    # Calibrated so `saturation` matches ≈ 80
    factor = saturation / 1.6  # ln(5) ≈ 1.6, so saturation matches → 80%
    score = 100.0 * (1.0 - math.exp(-count / factor))
    return min(score, 100.0)


def _tfidf_similarity(text_a: str, text_b: str) -> float:
    """Cosine similarity between two documents using TF-IDF.

    Falls back to simple keyword overlap if scikit-learn is unavailable.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(stop_words="english", max_features=5000)
        tfidf = vec.fit_transform([text_a, text_b])
        sim = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return float(sim)
    except ImportError:
        # Fallback: word-set overlap
        words_a = set(re.findall(r"\w+", text_a.lower()))
        words_b = set(re.findall(r"\w+", text_b.lower()))
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)


def _salary_score(
    salary_min: float | None,
    salary_max: float | None,
    jd_text: str,
    min_base: int = 190_000,
    target_tc: int = 300_000,
    high_comp_signals: list[str] | None = None,
) -> float:
    """Estimate comp-potential score (0-100)."""
    # If salary data is available, use it directly
    if salary_max and salary_max > 0:
        if salary_max >= target_tc:
            return 95.0
        if salary_max >= min_base:
            return 75.0
        if salary_max >= min_base * 0.8:
            return 50.0
        if salary_max >= min_base * 0.6:
            return 30.0
        return 15.0

    # No salary data — infer from company / level signals in JD
    signals = high_comp_signals if high_comp_signals is not None else HIGH_COMP_SIGNALS
    if not signals:
        return 50.0  # neutral when no signals configured (e.g. entry-level)
    jd_lower = jd_text.lower()
    score = 40.0  # neutral default when no salary info
    for sig in signals:
        if sig in jd_lower:
            score += 10.0
    return min(score, 100.0)


def score_job_basic(
    job_description: str,
    resume_text: str,
    *,
    job_title: str = "",
    company: str = "",
    salary_min: float | None = None,
    salary_max: float | None = None,
    is_remote: bool = False,
    config: dict[str, Any] | None = None,
) -> dict:
    """Score a job against the resume using keywords + TF-IDF.

    Returns a dict matching the ``JobScore`` schema fields so it can be
    saved directly to the database.
    """
    cfg = config or {}
    weights = cfg.get("scoring", {})
    w_tech = weights.get("technical_skills", 0.25)
    w_lead = weights.get("leadership_signal", 0.15)
    w_comp = weights.get("comp_potential", 0.12)
    w_plat = weights.get("platform_building", 0.13)
    w_traj = weights.get("company_trajectory", 0.10)
    w_cult = weights.get("culture_fit", 0.10)
    w_prog = weights.get("career_progression", 0.15)

    # Read keyword lists from profile config, fall back to module constants
    kw = cfg.get("keywords", {})
    tech_keywords = kw.get("technical", TECHNICAL_KEYWORDS)
    lead_keywords = kw.get("leadership", LEADERSHIP_KEYWORDS)
    plat_keywords = kw.get("platform_building", PLATFORM_BUILDING_KEYWORDS)
    comp_signals = kw.get("high_comp_signals", HIGH_COMP_SIGNALS)

    combined = f"{job_title} {company} {job_description}"

    # -- Dimension scores (0-100 each) ------------------------------------

    # Technical: blend TF-IDF resume↔JD similarity with keyword matches
    tfidf_raw = _tfidf_similarity(resume_text, job_description)
    # Scale TF-IDF: 0.15 similarity ≈ 60/100, 0.30 ≈ 90/100
    tech_tfidf = min(tfidf_raw * 300, 100.0)
    tech_kw = _keyword_score(combined, tech_keywords, saturation=6)
    technical = tech_tfidf * 0.5 + tech_kw * 0.5

    # Leadership: how many leadership signals are present
    leadership = _keyword_score(combined, lead_keywords, saturation=3)

    # Compensation potential
    comp_potential = _salary_score(
        salary_min,
        salary_max,
        combined,
        min_base=cfg.get("compensation", {}).get("min_base", 190_000),
        target_tc=cfg.get("compensation", {}).get("target_total_comp", 300_000),
        high_comp_signals=comp_signals,
    )

    # Platform building opportunity
    platform = _keyword_score(combined, plat_keywords, saturation=2)

    # Company trajectory — hiring/growth signals
    traj_signals = ["series a", "series b", "series c", "raised", "funded",
                    "growing", "scaling", "hiring", "expanding"]
    trajectory = _keyword_score(combined, traj_signals, saturation=2)

    # Culture fit
    culture_signals = ["remote", "flexible", "async", "collaborative",
                       "open source", "modern", "inclusive", "diversity"]
    culture = _keyword_score(combined, culture_signals, saturation=3)
    if is_remote:
        culture = min(culture + 25, 100.0)

    # Career progression
    progression = _career_progression_score(
        job_title, job_description, salary_min, salary_max, cfg,
    )

    overall = (
        technical * w_tech
        + leadership * w_lead
        + comp_potential * w_comp
        + platform * w_plat
        + trajectory * w_traj
        + culture * w_cult
        + progression * w_prog
    )

    # Configurable recommendation thresholds
    thresholds = weights.get("thresholds", {})
    strong_thresh = thresholds.get("strong_apply", 70)
    apply_thresh = thresholds.get("apply", 55)
    maybe_thresh = thresholds.get("maybe", 40)

    if overall >= strong_thresh:
        rec = "STRONG_APPLY"
    elif overall >= apply_thresh:
        rec = "APPLY"
    elif overall >= maybe_thresh:
        rec = "MAYBE"
    else:
        rec = "SKIP"

    # Strengths & gaps
    strengths: list[str] = []
    gaps: list[str] = []
    if technical >= 50:
        strengths.append("Good technical keyword match")
    elif technical >= 30:
        strengths.append("Some technical overlap")
    else:
        gaps.append("Low technical overlap with JD")
    if leadership >= 40:
        strengths.append("Leadership signals present")
    if platform >= 30:
        strengths.append("Platform-building opportunity")
    if comp_potential >= 70:
        strengths.append("Compensation likely meets target")
    elif comp_potential < 40:
        gaps.append("Comp may be below target")
    if is_remote:
        strengths.append("Remote position")
    if progression >= 60:
        strengths.append("Career upgrade opportunity")
    elif progression < 35:
        gaps.append("May be lateral or downgrade")

    return {
        "overall_score": round(overall, 1),
        "technical_score": round(technical, 1),
        "leadership_score": round(leadership, 1),
        "comp_potential_score": round(comp_potential, 1),
        "platform_building_score": round(platform, 1),
        "company_trajectory_score": round(trajectory, 1),
        "culture_fit_score": round(culture, 1),
        "career_progression_score": round(progression, 1),
        "recommendation": rec,
        "score_reasoning": f"Basic keyword scoring: {overall:.0f}/100 overall. "
                           f"Technical match {technical:.0f}, leadership {leadership:.0f}, "
                           f"comp potential {comp_potential:.0f}, career progression {progression:.0f}.",
        "key_strengths": strengths,
        "key_gaps": gaps,
    }
