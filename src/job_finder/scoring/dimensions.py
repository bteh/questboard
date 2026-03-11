"""Individual dimension scoring functions (0–100 each).

Each function takes raw text / metadata and returns a float score.
Company tier baselines are applied in ``core.score_job_basic``, not here.
"""

from __future__ import annotations

import re

from job_finder.scoring.helpers import keyword_score, salary_score, tfidf_similarity
from job_finder.scoring.signals import (
    CULTURE_ENTERPRISE_SIGNALS,
    CULTURE_STARTUP_SIGNALS,
    LEVEL_MAP,
    MGMT_SIGNALS,
    SCOPE_KEYWORDS,
    TRAJECTORY_ENTERPRISE_SIGNALS,
    TRAJECTORY_STARTUP_SIGNALS,
)


# ── Technical skills ──────────────────────────────────────────────────────

def score_technical(
    resume_text: str,
    job_description: str,
    combined: str,
    tech_keywords: list[str],
) -> float:
    """Blend TF-IDF resume↔JD similarity with keyword matches."""
    tfidf_raw = tfidf_similarity(resume_text, job_description)
    tech_tfidf = min(tfidf_raw * 300, 100.0)
    tech_kw = keyword_score(combined, tech_keywords, saturation=6)
    return tech_tfidf * 0.5 + tech_kw * 0.5


# ── Leadership ────────────────────────────────────────────────────────────

def score_leadership(combined: str, lead_keywords: list[str]) -> float:
    return keyword_score(combined, lead_keywords, saturation=3)


# ── Compensation potential ────────────────────────────────────────────────

def score_comp(
    salary_min: float | None,
    salary_max: float | None,
    combined: str,
    comp_signals: list[str],
    min_base: int = 80_000,
    target_tc: int = 150_000,
) -> float:
    return salary_score(
        salary_min, salary_max, combined,
        min_base=min_base, target_tc=target_tc,
        high_comp_signals=comp_signals,
    )


# ── Platform building ─────────────────────────────────────────────────────

def score_platform(combined: str, plat_keywords: list[str]) -> float:
    return keyword_score(combined, plat_keywords, saturation=3)


# ── Company trajectory ────────────────────────────────────────────────────

def score_trajectory(combined: str) -> float:
    all_signals = TRAJECTORY_STARTUP_SIGNALS + TRAJECTORY_ENTERPRISE_SIGNALS
    return keyword_score(combined, all_signals, saturation=3)


# ── Culture fit ───────────────────────────────────────────────────────────

def score_culture(combined: str, is_remote: bool) -> float:
    all_signals = CULTURE_STARTUP_SIGNALS + CULTURE_ENTERPRISE_SIGNALS
    score = keyword_score(combined, all_signals, saturation=4)
    if is_remote:
        score = min(score + 20, 100.0)
    return score


# ── Career progression ────────────────────────────────────────────────────

def _extract_level(title: str) -> float:
    """Extract a numeric level from a job title."""
    title_lower = title.lower()
    matched: list[float] = []
    for keyword, level in LEVEL_MAP.items():
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, title_lower):
            matched.append(level)
    return max(matched) if matched else 2.0


def score_career_progression(
    job_title: str,
    job_description: str,
    salary_min: float | None,
    salary_max: float | None,
    config: dict,
) -> float:
    """Score whether this job represents a career upgrade (0–100)."""
    baseline = config.get("career_baseline", {})
    current_level = _extract_level(baseline.get("current_title", "software engineer"))
    current_tc = baseline.get("current_tc", 100_000)
    job_level = _extract_level(job_title)

    score = 50.0  # neutral

    # Title escalation (+30 / -40)
    level_diff = job_level - current_level
    if level_diff > 0:
        score += min(level_diff * 15, 30)
    elif level_diff < 0:
        score += max(level_diff * 20, -40)

    # Scope expansion (+20)
    combined = f"{job_title} {job_description}".lower()
    scope_matches = sum(1 for kw in SCOPE_KEYWORDS if kw in combined)
    score += min(scope_matches * 5, 20)

    # Comp upgrade (+20 / -15)
    if salary_max and salary_max > 0:
        if salary_max > current_tc * 1.3:
            score += 20
        elif salary_max > current_tc * 1.1:
            score += 10
        elif salary_max < current_tc * 0.85:
            score -= 15

    # IC→manager transition bonus
    title_lower = job_title.lower()
    is_mgmt = any(
        re.search(r'\b' + re.escape(sig) + r'\b', title_lower)
        for sig in MGMT_SIGNALS
    )
    if is_mgmt and current_level <= 4:
        score += 10

    return max(0.0, min(score, 100.0))
