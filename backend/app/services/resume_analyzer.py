"""Resume analyzer — LLM-powered skill extraction and profile auto-configuration.

When a user uploads their resume, this module uses the LLM to extract:
- Core skills (technical, domain-specific, soft skills)
- Current seniority level
- Industry / domain
- Suggested target roles and search keywords

The extracted data is used to auto-populate profile keywords, target roles,
and scoring configuration so the app works for ANY profession without
manual YAML editing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are an expert career analyst. Analyze this resume and extract structured
information that will be used to configure a job search platform.

The candidate could be from ANY profession — engineering, marketing, sales,
healthcare, education, design, finance, operations, legal, etc. Do not assume
any particular industry.

Return **valid JSON** (no markdown fences):

{
  "industry": "<primary industry: technology, healthcare, finance, marketing, education, legal, etc.>",
  "seniority": "<one of: intern, junior, mid, senior, staff, principal, manager, director, vp, executive>",
  "current_title": "<their most recent job title>",
  "years_experience": <number>,

  "skills": [
    "<skill 1>", "<skill 2>", ...
  ],

  "leadership_signals": [
    "<leadership keyword from their experience, e.g. 'managed team of 7', 'built the team'>",
    ...
  ],

  "suggested_target_roles": [
    "<role title they'd likely search for>",
    ...
  ],

  "suggested_keywords": [
    "<industry-specific search term>",
    ...
  ],

  "high_comp_signals": [
    "<company names, level indicators, or comp signals from their background>",
    ...
  ]
}

Rules:
- Extract skills AS THEY APPEAR on the resume (preserve domain language)
- Include both hard skills (tools, technologies, certifications) and domain skills
- suggested_target_roles should include current-level AND next-level-up roles
- suggested_keywords should be industry-specific terms that would find relevant jobs
- Keep each list to 15-20 items max, prioritized by relevance
- leadership_signals should be phrases/patterns to look for in job descriptions
"""


def analyze_resume(resume_text: str, llm: Any | None = None) -> dict | None:
    """Extract structured profile data from resume text using LLM.

    Parameters
    ----------
    resume_text : str
        The full text of the parsed resume.
    llm : LLMClient or None
        When None, returns None (graceful degradation).

    Returns
    -------
    dict or None
        Extracted profile data, or None if LLM is unavailable.
    """
    if not llm or not getattr(llm, "is_configured", False):
        logger.info("No LLM configured — skipping resume analysis")
        return None

    if not resume_text or resume_text.startswith("ERROR"):
        return None

    system_prompt = (
        "You are a career analysis expert. Extract structured information "
        "from resumes across ALL industries and professions."
    )
    user_msg = f"{_EXTRACTION_PROMPT}\n\n=== RESUME ===\n{resume_text}"

    try:
        result = llm.chat_json(system_prompt, user_msg)
        if not result or not isinstance(result, dict):
            logger.warning("Resume analysis returned invalid result")
            return None

        logger.info(
            "Resume analysis complete: industry=%s, seniority=%s, %d skills extracted",
            result.get("industry", "unknown"),
            result.get("seniority", "unknown"),
            len(result.get("skills", [])),
        )
        return result
    except Exception as e:
        logger.warning("Resume analysis failed (non-fatal): %s", e)
        return None


def apply_analysis_to_profile(profile_config: dict, analysis: dict) -> dict:
    """Merge LLM-extracted resume data into a profile config dict.

    Only fills in fields that are empty/default — never overwrites
    user-customized values.

    Parameters
    ----------
    profile_config : dict
        The current profile YAML config.
    analysis : dict
        Output from ``analyze_resume()``.

    Returns
    -------
    dict
        Updated profile config.
    """
    if not analysis:
        return profile_config

    cfg = dict(profile_config)  # shallow copy

    # Auto-fill target_roles if empty or still has template defaults
    current_roles = cfg.get("target_roles", [])
    if not current_roles or current_roles == [""] or current_roles == ["software engineer", "data analyst"]:
        suggested = analysis.get("suggested_target_roles", [])
        if suggested:
            cfg["target_roles"] = suggested[:15]

    # Auto-fill keyword_searches if empty
    current_kw = cfg.get("keyword_searches", [])
    if not current_kw or current_kw == [""]:
        suggested = analysis.get("suggested_keywords", [])
        if suggested:
            cfg["keyword_searches"] = suggested[:10]

    # Auto-fill keywords.technical if empty or still has template defaults
    keywords = cfg.get("keywords", {})
    current_tech = keywords.get("technical", [])
    if not current_tech or current_tech == [""]:
        skills = analysis.get("skills", [])
        if skills:
            keywords["technical"] = skills[:20]

    # Auto-fill keywords.leadership if empty
    current_lead = keywords.get("leadership", [])
    if not current_lead or current_lead == ["mentorship", "lead", "manager"]:
        signals = analysis.get("leadership_signals", [])
        if signals:
            keywords["leadership"] = signals[:10]

    # Auto-fill high_comp_signals if empty
    current_comp = keywords.get("high_comp_signals", [])
    if not current_comp:
        comp_signals = analysis.get("high_comp_signals", [])
        if comp_signals:
            keywords["high_comp_signals"] = comp_signals[:10]

    cfg["keywords"] = keywords

    # Auto-fill career_baseline if empty
    baseline = cfg.get("career_baseline", {})
    if not baseline.get("current_title"):
        baseline["current_title"] = analysis.get("current_title", "")
    if baseline.get("current_level", "mid") == "mid" and analysis.get("seniority"):
        baseline["current_level"] = analysis["seniority"]
    cfg["career_baseline"] = baseline

    # Store the raw analysis for reference
    cfg["_resume_analysis"] = {
        "industry": analysis.get("industry", ""),
        "seniority": analysis.get("seniority", ""),
        "years_experience": analysis.get("years_experience", 0),
    }

    return cfg
