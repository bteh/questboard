"""Low-level scoring helpers: keyword matching, TF-IDF, salary estimation."""

from __future__ import annotations

import math
import re

from job_finder.scoring.signals import HIGH_COMP_SIGNALS, expand_aliases

PAY_PERIOD_FACTORS: dict[str, float] = {
    "hourly": 2080.0,
    "daily": 260.0,
    "weekly": 52.0,
    "monthly": 12.0,
    "annual": 1.0,
    "yearly": 1.0,
}


def annualize_amount(amount: float | int | None, period: str | None) -> float | None:
    """Convert an amount into an annualized number when the period is known."""
    if amount is None:
        return None
    try:
        numeric = float(amount)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    factor = PAY_PERIOD_FACTORS.get((period or "annual").lower())
    if factor is None:
        return None
    return numeric * factor


# ── Keyword helpers ───────────────────────────────────────────────────────

# Alphanumeric forms this short get word-boundary matching so "ML" can't
# match inside "HTML". Longer terms keep the historical substring behavior.
_SHORT_FORM_MAX_LEN = 3


def _form_in_text(text_lower: str, form: str) -> bool:
    form = form.strip().lower()
    if not form:
        return False
    if len(form) <= _SHORT_FORM_MAX_LEN and form.isalnum():
        return re.search(r"\b" + re.escape(form) + r"\b", text_lower) is not None
    return form in text_lower


def keyword_matches(text: str, keywords: list[str]) -> list[str]:
    """Return the configured keywords whose alias forms appear in *text*.

    Each keyword matches when ANY of its alias forms (see
    ``signals.expand_aliases``) appears, so a profile skill "ML" matches a
    JD that says "Machine Learning" and vice versa.
    """
    text_lower = text.lower()
    expanded = expand_aliases(keywords)
    matched: list[str] = []
    for kw in keywords:
        forms = expanded.get(kw, [kw])
        if any(_form_in_text(text_lower, form) for form in forms):
            matched.append(kw)
    return matched


def keyword_count(text: str, keywords: list[str]) -> int:
    """Return the number of keywords found in *text* (case-insensitive)."""
    return len(keyword_matches(text, keywords))


def keyword_score(
    text: str,
    keywords: list[str],
    saturation: int = 5,
    *,
    extra_hits: int = 0,
    return_matches: bool = False,
) -> float | tuple[float, list[str]]:
    """Score keyword matches on a 0–100 scale with diminishing returns.

    Uses a saturation curve: finding *saturation* keywords gives ~80/100.
    ``extra_hits`` adds synthetic hits to the count (e.g. matched
    certifications counted as strong technical hits). With
    ``return_matches=True`` returns ``(score, matched_keywords)``.
    """
    matched = keyword_matches(text, keywords)
    count = len(matched) + max(int(extra_hits), 0)
    if count == 0:
        score = 0.0
    else:
        # Asymptotic curve calibrated so `saturation` matches → 80%
        factor = saturation / 1.6  # ln(5) ≈ 1.6
        score = min(100.0 * (1.0 - math.exp(-count / factor)), 100.0)
    if return_matches:
        return score, matched
    return score


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
    salary_period: str | None = None,
) -> float:
    """Estimate comp-potential score (0–100)."""
    annual_salary_max = annualize_amount(salary_max, salary_period) if salary_period else salary_max
    if annual_salary_max and annual_salary_max > 0:
        if annual_salary_max > target_tc * 2:
            # Way above target — likely a more senior role than user can land
            return 40.0
        if annual_salary_max >= target_tc:
            return 95.0
        if annual_salary_max >= min_base:
            return 75.0
        if annual_salary_max >= min_base * 0.8:
            return 50.0
        if annual_salary_max >= min_base * 0.6:
            return 30.0
        return 15.0

    # No salary data — infer from signals in JD
    signals = high_comp_signals if high_comp_signals is not None else HIGH_COMP_SIGNALS
    if not signals:
        return 50.0
    score = 40.0 + 10.0 * len(keyword_matches(jd_text, list(signals)))
    return min(score, 100.0)
