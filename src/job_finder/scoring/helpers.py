"""Low-level scoring helpers: keyword matching, TF-IDF, salary estimation."""

from __future__ import annotations

import math
import re

from job_finder.scoring.signals import HIGH_COMP_SIGNALS


# ── Keyword helpers ───────────────────────────────────────────────────────

def keyword_count(text: str, keywords: list[str]) -> int:
    """Return the number of keywords found in *text* (case-insensitive)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def keyword_score(text: str, keywords: list[str], saturation: int = 5) -> float:
    """Score keyword matches on a 0–100 scale with diminishing returns.

    Uses a saturation curve: finding *saturation* keywords gives ~80/100.
    """
    count = keyword_count(text, keywords)
    if count == 0:
        return 0.0
    # Asymptotic curve calibrated so `saturation` matches → 80%
    factor = saturation / 1.6  # ln(5) ≈ 1.6
    score = 100.0 * (1.0 - math.exp(-count / factor))
    return min(score, 100.0)


# ── TF-IDF similarity ────────────────────────────────────────────────────

def tfidf_similarity(text_a: str, text_b: str) -> float:
    """Cosine similarity between two documents using TF-IDF.

    Falls back to simple word-set overlap if scikit-learn is unavailable.
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(stop_words="english", max_features=5000)
        tfidf = vec.fit_transform([text_a, text_b])
        sim = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return float(sim)
    except ImportError:
        words_a = set(re.findall(r"\w+", text_a.lower()))
        words_b = set(re.findall(r"\w+", text_b.lower()))
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)


# ── Salary / comp estimation ─────────────────────────────────────────────

def salary_score(
    salary_min: float | None,
    salary_max: float | None,
    jd_text: str,
    min_base: int = 80_000,
    target_tc: int = 150_000,
    high_comp_signals: list[str] | None = None,
) -> float:
    """Estimate comp-potential score (0–100)."""
    if salary_max and salary_max > 0:
        if salary_max > target_tc * 2:
            # Way above target — likely a more senior role than user can land
            return 40.0
        if salary_max >= target_tc:
            return 95.0
        if salary_max >= min_base:
            return 75.0
        if salary_max >= min_base * 0.8:
            return 50.0
        if salary_max >= min_base * 0.6:
            return 30.0
        return 15.0

    # No salary data — infer from signals in JD
    signals = high_comp_signals if high_comp_signals is not None else HIGH_COMP_SIGNALS
    if not signals:
        return 50.0
    jd_lower = jd_text.lower()
    score = 40.0
    for sig in signals:
        if sig in jd_lower:
            score += 10.0
    return min(score, 100.0)
