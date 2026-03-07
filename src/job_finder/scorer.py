"""Keyword / TF-IDF based job scorer — works without any LLM.

Provides a baseline score by comparing resume text against a job description
using cosine similarity and domain-specific keyword checks.
"""

from __future__ import annotations

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
]


def _keyword_overlap(text: str, keywords: list[str]) -> float:
    """Return fraction of *keywords* found in *text* (case-insensitive)."""
    text_lower = text.lower()
    if not keywords:
        return 0.0
    found = sum(1 for kw in keywords if kw.lower() in text_lower)
    return found / len(keywords)


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
) -> float:
    """Estimate comp-potential score (0-100)."""
    # If salary data is available, use it directly
    if salary_max and salary_max > 0:
        if salary_max >= target_tc:
            return 95.0
        if salary_max >= min_base:
            return 70.0
        if salary_max >= min_base * 0.8:
            return 45.0
        return 20.0

    # No salary data — infer from company / level signals in JD
    jd_lower = jd_text.lower()
    score = 50.0  # neutral default
    for sig in HIGH_COMP_SIGNALS:
        if sig in jd_lower:
            score += 8.0
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
    w_tech = weights.get("technical_skills", 0.30)
    w_lead = weights.get("leadership_signal", 0.20)
    w_comp = weights.get("comp_potential", 0.15)
    w_plat = weights.get("platform_building", 0.15)
    w_traj = weights.get("company_trajectory", 0.10)
    w_cult = weights.get("culture_fit", 0.10)

    combined = f"{job_title} {company} {job_description}"

    # Dimension scores (0-100 each)
    tech_raw = _tfidf_similarity(resume_text, job_description) * 100
    tech_kw = _keyword_overlap(combined, TECHNICAL_KEYWORDS) * 100
    technical = min(tech_raw * 0.6 + tech_kw * 0.4, 100.0)

    leadership = _keyword_overlap(combined, LEADERSHIP_KEYWORDS) * 100

    comp_potential = _salary_score(
        salary_min,
        salary_max,
        combined,
        min_base=cfg.get("compensation", {}).get("min_base", 190_000),
        target_tc=cfg.get("compensation", {}).get("target_total_comp", 300_000),
    )

    platform = _keyword_overlap(combined, PLATFORM_BUILDING_KEYWORDS) * 100

    # Company trajectory — rough heuristic (hiring + growth signals)
    traj_signals = ["series a", "series b", "series c", "raised", "funded",
                    "growing", "scaling", "hiring", "expanding"]
    trajectory = _keyword_overlap(combined, traj_signals) * 100

    # Culture fit
    culture_signals = ["remote", "flexible", "async", "collaborative",
                       "open source", "modern", "inclusive", "diversity"]
    culture = _keyword_overlap(combined, culture_signals) * 100
    if is_remote:
        culture = min(culture + 20, 100.0)

    overall = (
        technical * w_tech
        + leadership * w_lead
        + comp_potential * w_comp
        + platform * w_plat
        + trajectory * w_traj
        + culture * w_cult
    )

    # Recommendation
    if overall >= 80:
        rec = "STRONG_APPLY"
    elif overall >= 65:
        rec = "APPLY"
    elif overall >= 50:
        rec = "MAYBE"
    else:
        rec = "SKIP"

    # Strengths & gaps
    strengths: list[str] = []
    gaps: list[str] = []
    if technical >= 60:
        strengths.append("Good technical keyword match")
    else:
        gaps.append("Low technical overlap with JD")
    if leadership >= 40:
        strengths.append("Leadership signals present")
    if platform >= 30:
        strengths.append("Platform-building opportunity")
    if comp_potential >= 70:
        strengths.append("Compensation likely meets target")
    else:
        gaps.append("Comp may be below $300K target")

    return {
        "overall_score": round(overall, 1),
        "technical_score": round(technical, 1),
        "leadership_score": round(leadership, 1),
        "comp_potential_score": round(comp_potential, 1),
        "platform_building_score": round(platform, 1),
        "company_trajectory_score": round(trajectory, 1),
        "culture_fit_score": round(culture, 1),
        "recommendation": rec,
        "score_reasoning": f"Basic keyword scoring: {overall:.0f}/100 overall. "
                           f"Technical match {technical:.0f}, leadership {leadership:.0f}, "
                           f"comp potential {comp_potential:.0f}.",
        "key_strengths": strengths,
        "key_gaps": gaps,
    }
