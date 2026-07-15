"""Main entry point for keyword-based job scoring.

Orchestrates dimension scorers, applies company tier baselines,
and produces the final score dict compatible with the DB schema.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

from job_finder.scoring.dimensions import (
    effective_trajectory_keywords,
    score_career_progression,
    score_comp,
    score_culture,
    score_leadership,
    score_platform,
    score_technical,
    score_trajectory,
)
from job_finder.scoring.helpers import annualize_amount, keyword_matches
from job_finder.scoring.signals import (
    CULTURE_ENTERPRISE_SIGNALS,
    CULTURE_STARTUP_SIGNALS,
    HIGH_COMP_SIGNALS,
    LEADERSHIP_KEYWORDS,
    PLATFORM_BUILDING_KEYWORDS,
    TECHNICAL_KEYWORDS,
    TIER_BASELINES,
)

# Tokens that mark a certification/licensure requirement in a JD when they
# appear near required/must-have language.
_CERT_TOKENS = ("certification", "certified", "certificate", "licensure", "license")
_REQUIRED_RE = re.compile(r"required|must[- ]have|must hold|requirement")


def _jd_requires_missing_cert(jd_text: str, cert_matches: list[str]) -> bool:
    """True when the JD demands a cert-like token the profile doesn't cover."""
    if cert_matches:
        return False
    jd_lower = jd_text.lower()
    for m in _REQUIRED_RE.finditer(jd_lower):
        window = jd_lower[max(0, m.start() - 120):m.end() + 120]
        if any(token in window for token in _CERT_TOKENS):
            return True
    return False


def _dimension_evidence(
    keywords: list[str], matched: list[str],
) -> dict[str, list[str]]:
    matched_lower = {m.lower() for m in matched}
    missing_top = [kw for kw in keywords if kw.lower() not in matched_lower][:5]
    return {"matched": matched, "missing_top": missing_top}


def score_job_basic(
    job_description: str,
    resume_text: str,
    *,
    job_title: str = "",
    company: str = "",
    company_type: str = "Unknown",
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_period: str = "",
    is_remote: bool = False,
    config: dict[str, Any] | None = None,
    company_baselines: dict[str, float] | None = None,
) -> dict:
    """Score a job against the resume using keywords + TF-IDF.

    Parameters
    ----------
    company_type : str
        Tier from ``classify_company()`` — used to look up static baselines.
    company_baselines : dict, optional
        LLM-generated baselines from ``company_intel.get_company_baselines()``.
        When provided, these override the static tier baselines for a more
        accurate per-company score.
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

    # Validate weights sum to 1.0 (misconfigured profiles can inflate scores)
    total_weight = w_tech + w_lead + w_comp + w_plat + w_traj + w_cult + w_prog
    if abs(total_weight - 1.0) > 0.01:
        logger.warning("Scoring weights sum to %.2f (expected 1.0) — normalizing", total_weight)
        w_tech /= total_weight
        w_lead /= total_weight
        w_comp /= total_weight
        w_plat /= total_weight
        w_traj /= total_weight
        w_cult /= total_weight
        w_prog /= total_weight

    # Keyword overrides from profile config — profiles can provide
    # domain-specific keywords so scoring works for any profession
    kw = cfg.get("keywords", {})
    tech_keywords = kw.get("technical", TECHNICAL_KEYWORDS)
    lead_keywords = kw.get("leadership", LEADERSHIP_KEYWORDS)
    plat_keywords = kw.get("platform_building", PLATFORM_BUILDING_KEYWORDS)
    comp_signals = kw.get("high_comp_signals", HIGH_COMP_SIGNALS)
    traj_keywords = kw.get("company_trajectory") or None  # None = use defaults
    culture_keywords = kw.get("culture_fit") or None  # None = use defaults

    # Resume analysis metadata (written during resume upload) calibrates
    # keyword scoring; everything degrades to pre-existing behavior when absent.
    ra = cfg.get("_resume_analysis") or {}
    years_experience = ra.get("years_experience")
    seniority = ra.get("seniority")
    industry = ra.get("industry")

    # Profile certifications: a JD mentioning one counts as a strong
    # technical keyword hit.
    certifications = [
        c for c in (cfg.get("certifications") or [])
        if isinstance(c, str) and c.strip()
    ]

    # When include_equity is false, strip equity-specific signals from comp scoring
    include_equity = cfg.get("compensation", {}).get("include_equity", True)
    compensation_cfg = cfg.get("compensation", {})
    user_pay_period = compensation_cfg.get("pay_period", "annual")
    normalized_min_base = annualize_amount(compensation_cfg.get("min_base", 80_000), user_pay_period) or 80_000
    normalized_target_tc = annualize_amount(compensation_cfg.get("target_total_comp", 150_000), user_pay_period) or 150_000
    if not include_equity:
        _equity_signals = {
            "equity", "rsu", "stock options", "signing bonus",
            "competitive compensation", "total compensation",
        }
        comp_signals = [s for s in comp_signals if s.lower() not in _equity_signals]

    combined = f"{job_title} {company} {job_description}"

    # Baselines: prefer LLM company intel → fall back to static tier
    has_ai_intel = company_baselines is not None
    baselines = company_baselines or TIER_BASELINES.get(company_type, TIER_BASELINES["Unknown"])

    # ── Dimension scores (0–100 each) ─────────────────────────────────

    cert_matches = keyword_matches(combined, certifications) if certifications else []

    tech_kw = score_technical(
        resume_text, job_description, combined, tech_keywords,
        years_experience=years_experience,
        extra_keyword_hits=2 * len(cert_matches),
    )
    lead_kw = score_leadership(
        combined, lead_keywords, years_experience=years_experience,
    )

    comp_kw = score_comp(
        salary_min, salary_max, combined, comp_signals,
        min_base=int(normalized_min_base),
        target_tc=int(normalized_target_tc),
        salary_period=salary_period,
    )
    plat_kw = score_platform(combined, plat_keywords)
    traj_kw = score_trajectory(
        combined, trajectory_keywords=traj_keywords, industry=industry,
    )
    culture_kw = score_culture(combined, is_remote, culture_keywords=culture_keywords)

    # ── Per-dimension keyword evidence ────────────────────────────────
    traj_effective = effective_trajectory_keywords(traj_keywords, industry=industry)
    culture_effective = culture_keywords or (
        CULTURE_STARTUP_SIGNALS + CULTURE_ENTERPRISE_SIGNALS
    )
    evidence = {
        "technical_skills": _dimension_evidence(
            tech_keywords, keyword_matches(combined, tech_keywords) + cert_matches,
        ),
        "leadership_signal": _dimension_evidence(
            lead_keywords, keyword_matches(combined, lead_keywords),
        ),
        "platform_building": _dimension_evidence(
            plat_keywords, keyword_matches(combined, plat_keywords),
        ),
        "company_trajectory": _dimension_evidence(
            traj_effective, keyword_matches(combined, traj_effective),
        ),
        "culture_fit": _dimension_evidence(
            culture_effective, keyword_matches(combined, culture_effective),
        ),
        "comp_potential": _dimension_evidence(
            list(comp_signals), keyword_matches(combined, list(comp_signals)),
        ),
    }

    # Blend keyword scores with baselines:
    # - LLM intel: weighted blend (AI can lower scores, not just raise them)
    # - Static tier: weighted blend — keyword relevance matters most (70%),
    #   company tier provides a boost (30%).  Previous max() approach let
    #   company prestige override job relevance, inflating scores for
    #   irrelevant roles at well-known companies.
    if has_ai_intel:
        technical = tech_kw * 0.4 + baselines.get("technical", 0) * 0.6
        leadership = lead_kw * 0.4 + baselines.get("leadership", 0) * 0.6
        comp_potential = comp_kw * 0.4 + baselines.get("comp", 0) * 0.6
        platform = plat_kw * 0.4 + baselines.get("platform", 0) * 0.6
        trajectory = traj_kw * 0.4 + baselines.get("trajectory", 0) * 0.6
        culture = culture_kw * 0.4 + baselines.get("culture", 0) * 0.6
    else:
        technical = tech_kw * 0.7 + baselines.get("technical", 0) * 0.3
        leadership = lead_kw * 0.7 + baselines.get("leadership", 0) * 0.3
        comp_potential = comp_kw * 0.7 + baselines.get("comp", 0) * 0.3
        platform = plat_kw * 0.7 + baselines.get("platform", 0) * 0.3
        trajectory = traj_kw * 0.7 + baselines.get("trajectory", 0) * 0.3
        culture = culture_kw * 0.7 + baselines.get("culture", 0) * 0.3

    progression = score_career_progression(
        job_title, job_description, salary_min, salary_max, cfg,
        salary_period=salary_period,
        seniority=seniority,
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

    # Recommendation thresholds
    thresholds = weights.get("thresholds", {})
    strong_thresh = thresholds.get("strong_apply", 70)
    apply_thresh = thresholds.get("apply", 55)
    maybe_thresh = thresholds.get("maybe", 40)

    # Keyword-only scoring is structurally low (TF-IDF can't capture
    # semantic relevance), so we use gentler thresholds to avoid marking
    # good jobs as "Skip" just because the AI didn't score them. A
    # keyword score of 25+ typically means the job title and some terms
    # matched — that's at least a MAYBE, not a definitive SKIP.
    ai_scored = bool(company_baselines)
    if ai_scored:
        if overall >= strong_thresh:
            rec = "STRONG_APPLY"
        elif overall >= apply_thresh:
            rec = "APPLY"
        elif overall >= maybe_thresh:
            rec = "MAYBE"
        else:
            rec = "SKIP"
    else:
        # Keyword-only: shift thresholds down since scores are lower
        if overall >= strong_thresh * 0.65:
            rec = "STRONG_APPLY"
        elif overall >= apply_thresh * 0.55:
            rec = "APPLY"
        elif overall >= maybe_thresh * 0.5:
            rec = "MAYBE"
        else:
            rec = "SKIP"

    # Strengths & gaps
    source = "AI intel" if company_baselines else company_type
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
    if trajectory >= 60:
        strengths.append(f"Strong company trajectory ({source})")
    if culture >= 55:
        strengths.append("Good culture signals")
    if cert_matches:
        strengths.append(
            "Certification match: " + ", ".join(cert_matches[:3])
        )
    if _jd_requires_missing_cert(job_description, cert_matches):
        gaps.append("JD requires a certification not in your profile")

    scoring_method = "ai" if ai_scored else "keyword"

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
        "scoring_method": scoring_method,
        # This scorer is always the keyword scale, even when AI company intel
        # informed the baselines; the LLM path stamps 'ai' in the pipeline.
        "score_source": "keyword",
        "score_reasoning": (
            f"Scoring ({source}): {overall:.0f}/100 overall. "
            f"Technical {technical:.0f}, leadership {leadership:.0f}, "
            f"comp {comp_potential:.0f}, trajectory {trajectory:.0f}, "
            f"culture {culture:.0f}, progression {progression:.0f}."
            + ("" if ai_scored else " (keyword-only — AI scoring unavailable)")
        ),
        "key_strengths": strengths,
        "key_gaps": gaps,
        "score_evidence": evidence,
    }
