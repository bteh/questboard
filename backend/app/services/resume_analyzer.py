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

import copy
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PROFILE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "job_finder", "config", "profiles")
)
_AUTO_PROFILE_KEYS = (
    "target_roles",
    "keyword_searches",
    "keywords",
    "career_baseline",
    "_resume_analysis",
)

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


def _clean_list(values: Any, limit: int) -> list[str]:
    """Normalize a list-like value into a de-duplicated list of strings."""
    if not isinstance(values, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


def _normalize_level(value: Any) -> str:
    """Coerce legacy list-based level values into a single level string."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return "mid"
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "mid"


def apply_analysis_to_profile(
    profile_config: dict,
    analysis: dict,
    *,
    force_overwrite: bool = False,
) -> dict:
    """Merge LLM-extracted resume data into a profile config dict.

    When ``force_overwrite`` is true, resume-derived fields are refreshed even
    when they already have values. This is used after uploading a new resume
    or explicitly re-running analysis.

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

    cfg = copy.deepcopy(profile_config or {})

    suggested_roles = _clean_list(analysis.get("suggested_target_roles"), 15)
    suggested_keywords = _clean_list(analysis.get("suggested_keywords"), 10)
    extracted_skills = _clean_list(analysis.get("skills"), 20)
    leadership_signals = _clean_list(analysis.get("leadership_signals"), 10)
    high_comp_signals = _clean_list(analysis.get("high_comp_signals"), 10)
    current_title = str(analysis.get("current_title", "")).strip()
    seniority = str(analysis.get("seniority", "")).strip()

    current_roles = _clean_list(cfg.get("target_roles"), 100)
    if force_overwrite:
        if suggested_roles:
            cfg["target_roles"] = suggested_roles
    elif not current_roles and suggested_roles:
        cfg["target_roles"] = suggested_roles

    current_kw = _clean_list(cfg.get("keyword_searches"), 100)
    if force_overwrite:
        if suggested_keywords:
            cfg["keyword_searches"] = suggested_keywords
    elif not current_kw and suggested_keywords:
        cfg["keyword_searches"] = suggested_keywords

    keywords = dict(cfg.get("keywords") or {})
    current_tech = _clean_list(keywords.get("technical"), 100)
    if force_overwrite:
        if extracted_skills:
            keywords["technical"] = extracted_skills
    elif not current_tech and extracted_skills:
        keywords["technical"] = extracted_skills

    current_lead = _clean_list(keywords.get("leadership"), 100)
    if force_overwrite:
        if leadership_signals:
            keywords["leadership"] = leadership_signals
    elif not current_lead and leadership_signals:
        keywords["leadership"] = leadership_signals

    current_comp = _clean_list(keywords.get("high_comp_signals"), 100)
    if force_overwrite:
        if high_comp_signals:
            keywords["high_comp_signals"] = high_comp_signals
    elif not current_comp and high_comp_signals:
        keywords["high_comp_signals"] = high_comp_signals

    cfg["keywords"] = keywords

    baseline = dict(cfg.get("career_baseline") or {})
    baseline_level = _normalize_level(baseline.get("current_level"))
    baseline["current_level"] = baseline_level
    if force_overwrite:
        if current_title:
            baseline["current_title"] = current_title
        if seniority:
            baseline["current_level"] = seniority
    else:
        if not str(baseline.get("current_title", "")).strip() and current_title:
            baseline["current_title"] = current_title
        if baseline_level == "mid" and seniority:
            baseline["current_level"] = seniority
    cfg["career_baseline"] = baseline

    cfg["_resume_analysis"] = {
        "industry": analysis.get("industry", ""),
        "seniority": analysis.get("seniority", ""),
        "years_experience": analysis.get("years_experience", 0),
    }

    return cfg


def persist_analysis_to_profile(
    profile: str,
    analysis: dict,
    profile_config: dict | None = None,
    *,
    force_overwrite: bool = True,
) -> dict:
    """Persist resume-derived fields back into the profile YAML."""
    if not analysis:
        return profile_config or {}

    import yaml

    if profile_config is None:
        from app.dependencies import get_config

        profile_config = get_config(profile if profile != "default" else None)

    profile_path = os.path.join(_PROFILE_ROOT, f"{profile}.yaml")
    os.makedirs(_PROFILE_ROOT, exist_ok=True)

    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            persisted = yaml.safe_load(f) or {}
    else:
        persisted = copy.deepcopy(profile_config or {})

    updated = apply_analysis_to_profile(
        persisted or profile_config or {},
        analysis,
        force_overwrite=force_overwrite,
    )

    for key in _AUTO_PROFILE_KEYS:
        if key in updated:
            persisted[key] = updated[key]

    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(
            persisted,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    logger.info("Auto-configured profile '%s' from resume analysis", profile)
    return persisted
