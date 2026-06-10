"""FIX 1: cfg['_resume_analysis'] (years_experience / seniority / industry)
must influence keyword scoring instead of being dead metadata.
"""
from __future__ import annotations

import pytest

from job_finder.scoring.core import score_job_basic

_JD = (
    "We are hiring a data engineer to build data pipelines with Python, SQL, "
    "Airflow, Spark, and AWS."
)
_RESUME = "Data engineer experienced with Python, SQL, Airflow, Spark, and AWS."
_KEYWORDS = ["python", "sql", "airflow", "spark", "aws"]


def _cfg(**resume_analysis) -> dict:
    cfg: dict = {"keywords": {"technical": list(_KEYWORDS)}}
    if resume_analysis:
        cfg["_resume_analysis"] = resume_analysis
    return cfg


def _technical(cfg: dict) -> float:
    return score_job_basic(_JD, _RESUME, config=cfg)["technical_score"]


# ── years_experience → technical saturation ──────────────────────────────

@pytest.mark.parametrize(
    "junior_years,senior_years",
    [(0, 10), (2, 12), (5, 20)],
)
def test_senior_reaches_higher_technical_for_equal_hits(junior_years, senior_years):
    """Same JD + same keywords: more experience -> same hits score higher."""
    junior = _technical(_cfg(years_experience=junior_years))
    senior = _technical(_cfg(years_experience=senior_years))
    assert senior > junior


def test_technical_score_monotonic_in_years_experience():
    scores = [_technical(_cfg(years_experience=y)) for y in (0, 3, 5, 8, 10, 15, 20)]
    for prev, curr in zip(scores, scores[1:]):
        assert curr >= prev, f"technical score decreased: {scores}"


# ── seniority → career progression calibration ───────────────────────────

def test_seniority_calibrates_career_progression():
    """Without a career_baseline, _resume_analysis.seniority sets current level.

    A 'Senior' JD is a lateral move for a senior profile but an overreach
    for a junior one, so the senior profile must score higher.
    """
    senior = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer",
        config=_cfg(seniority="senior"),
    )
    junior = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer",
        config=_cfg(seniority="junior"),
    )
    assert senior["career_progression_score"] > junior["career_progression_score"]


def test_explicit_career_baseline_wins_over_seniority_fallback():
    cfg_junior_ra = _cfg(seniority="junior")
    cfg_junior_ra["career_baseline"] = {"current_title": "senior data engineer"}
    cfg_senior_ra = _cfg(seniority="senior")
    cfg_senior_ra["career_baseline"] = {"current_title": "senior data engineer"}

    with_junior_ra = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer", config=cfg_junior_ra,
    )
    with_senior_ra = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer", config=cfg_senior_ra,
    )
    assert (
        with_junior_ra["career_progression_score"]
        == with_senior_ra["career_progression_score"]
    )


# ── industry → trajectory keyword defaults ────────────────────────────────

def test_industry_extends_default_trajectory_keywords():
    jd = "Our hospital just earned Magnet designation and opened a new facility."
    with_industry = score_job_basic(jd, _RESUME, config=_cfg(industry="healthcare"))
    without = score_job_basic(jd, _RESUME, config=_cfg())
    assert (
        with_industry["company_trajectory_score"]
        > without["company_trajectory_score"]
    )


def test_profile_trajectory_keywords_override_industry_defaults():
    jd = "Our hospital just earned Magnet designation and opened a new facility."
    cfg_with = _cfg(industry="healthcare")
    cfg_with["keywords"]["company_trajectory"] = ["series z funding"]
    cfg_without = _cfg()
    cfg_without["keywords"]["company_trajectory"] = ["series z funding"]

    with_industry = score_job_basic(jd, _RESUME, config=cfg_with)
    without = score_job_basic(jd, _RESUME, config=cfg_without)
    assert (
        with_industry["company_trajectory_score"]
        == without["company_trajectory_score"]
    )


# ── regression guard: absent _resume_analysis = pre-change behavior ──────

def test_absent_resume_analysis_behaves_exactly_as_before():
    """Frozen values captured from the pre-change scorer."""
    result = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer", config=_cfg(),
    )
    assert result["technical_score"] == pytest.approx(66.8, abs=0.05)
    assert result["career_progression_score"] == pytest.approx(65.0, abs=0.05)


def test_empty_resume_analysis_equals_absent():
    cfg_empty = _cfg()
    cfg_empty["_resume_analysis"] = {}
    with_empty = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer", config=cfg_empty,
    )
    absent = score_job_basic(
        _JD, _RESUME, job_title="Senior Data Engineer", config=_cfg(),
    )
    for key in ("technical_score", "leadership_score", "career_progression_score",
                "company_trajectory_score", "overall_score"):
        assert with_empty[key] == absent[key]
