"""Individual dimension scoring functions (0\u2013100 each).

Each function takes raw text / metadata and returns a float score.
Company tier baselines are applied in ``core.score_job_basic``, not here.

When profile config provides domain-specific keywords (e.g. a nurse profile
with "patient care", "clinical protocols"), those are used instead of the
hardcoded defaults.  This makes scoring work for any profession.
"""

from __future__ import annotations

import re

from job_finder.scoring.helpers import annualize_amount, keyword_score, salary_score, tfidf_similarity
from job_finder.scoring.signals import (
    CULTURE_ENTERPRISE_SIGNALS,
    CULTURE_STARTUP_SIGNALS,
    LEVEL_MAP,
    MGMT_SIGNALS,
    SCOPE_KEYWORDS,
    TRAJECTORY_ENTERPRISE_SIGNALS,
    TRAJECTORY_STARTUP_SIGNALS,
)


# \u2500\u2500 Technical skills \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def score_technical(
    resume_text: str,
    job_description: str,
    combined: str,
    tech_keywords: list[str],
) -> float:
    """Blend TF-IDF resume\u2194JD similarity with keyword matches."""
    tfidf_raw = tfidf_similarity(resume_text, job_description)
    tech_tfidf = min(tfidf_raw * 300, 100.0)
    tech_kw = keyword_score(combined, tech_keywords, saturation=6)
    return tech_tfidf * 0.5 + tech_kw * 0.5


# \u2500\u2500 Leadership \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def score_leadership(combined: str, lead_keywords: list[str]) -> float:
    return keyword_score(combined, lead_keywords, saturation=3)


# \u2500\u2500 Compensation potential \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def score_comp(
    salary_min: float | None,
    salary_max: float | None,
    combined: str,
    comp_signals: list[str],
    min_base: int = 80_000,
    target_tc: int = 150_000,
    salary_period: str = "",
) -> float:
    return salary_score(
        salary_min, salary_max, combined,
        min_base=min_base, target_tc=target_tc,
        high_comp_signals=comp_signals,
        salary_period=salary_period,
    )


# \u2500\u2500 Platform building \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def score_platform(combined: str, plat_keywords: list[str]) -> float:
    return keyword_score(combined, plat_keywords, saturation=3)


# \u2500\u2500 Company trajectory \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def score_trajectory(
    combined: str,
    trajectory_keywords: list[str] | None = None,
) -> float:
    if trajectory_keywords:
        all_signals = trajectory_keywords
    else:
        all_signals = TRAJECTORY_STARTUP_SIGNALS + TRAJECTORY_ENTERPRISE_SIGNALS
    return keyword_score(combined, all_signals, saturation=3)


# \u2500\u2500 Culture fit \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def score_culture(
    combined: str,
    is_remote: bool,
    culture_keywords: list[str] | None = None,
) -> float:
    if culture_keywords:
        all_signals = culture_keywords
    else:
        all_signals = CULTURE_STARTUP_SIGNALS + CULTURE_ENTERPRISE_SIGNALS
    score = keyword_score(combined, all_signals, saturation=4)
    if is_remote:
        score = min(score + 20, 100.0)
    return score


# \u2500\u2500 Career progression \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

def _match_level(text: str) -> float | None:
    """Return the best-matching numeric level for text, if any."""
    if not text:
        return None

    title_lower = text.lower()
    matched: list[tuple[int, int, float]] = []  # (position, keyword_length, level)
    for keyword, level in LEVEL_MAP.items():
        pattern = r'\b' + re.escape(keyword) + r'\b'
        found = re.search(pattern, title_lower)
        if found:
            matched.append((found.start(), len(keyword), level))
    if not matched:
        return None

    # Prefer the earliest explicit level signal in the title.
    # When multiple matches start at the same position, prefer the longest phrase.
    matched.sort(key=lambda x: (x[0], -x[1]))
    return matched[0][2]


def _extract_level(title: str) -> float:
    """Extract a numeric level from a job title.

    Processes longer (more specific) keywords first so that e.g.
    "account executive" (level 2) is matched before the shorter
    "executive" phrases, and the most-specific match wins.
    """
    matched = _match_level(title)
    if matched is None:
        return 2.0
    return matched


def resolve_current_level(baseline: dict | None) -> float:
    """Resolve the user's current level from explicit level or title."""
    baseline = baseline or {}

    explicit_level = baseline.get("current_level")
    if isinstance(explicit_level, str):
        matched = _match_level(explicit_level.strip())
        if matched is not None:
            return matched

    current_title = baseline.get("current_title")
    if isinstance(current_title, str):
        matched = _match_level(current_title.strip())
        if matched is not None:
            return matched

    return 2.0


def score_career_progression(
    job_title: str,
    job_description: str,
    salary_min: float | None,
    salary_max: float | None,
    config: dict,
) -> float:
    """Score whether this job represents a career upgrade (0\u2013100)."""
    baseline = config.get("career_baseline", {})
    current_level = resolve_current_level(baseline)
    compensation_cfg = config.get("compensation", {})
    user_period = compensation_cfg.get("pay_period", "annual")
    current_tc = annualize_amount(baseline.get("current_tc", 100_000), user_period) or 100_000
    job_level = _extract_level(job_title)

    score = 50.0  # neutral

    # Title escalation: reward 1-level stretch, penalize overreach
    level_diff = job_level - current_level
    if 0 < level_diff <= 1.5:
        # Healthy stretch \u2014 one level up is ideal
        score += min(level_diff * 15, 25)
    elif level_diff > 1.5:
        # Overreach \u2014 job is too senior for this user
        score -= min((level_diff - 1) * 20, 40)
    elif level_diff < 0:
        # Step down
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

        # Penalty when salary is below min_acceptable_tc
        min_acceptable_tc = annualize_amount(baseline.get("min_acceptable_tc", current_tc), user_period) or current_tc
        if salary_max < min_acceptable_tc:
            score -= 20

    # IC\u2192manager transition bonus
    title_lower = job_title.lower()
    is_mgmt = any(
        re.search(r'\b' + re.escape(sig) + r'\b', title_lower)
        for sig in MGMT_SIGNALS
    )
    if is_mgmt and current_level <= 4:
        score += 10

    return max(0.0, min(score, 100.0))
