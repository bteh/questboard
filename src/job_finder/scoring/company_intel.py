"""LLM-powered company intelligence for scoring.

Uses the LLM's trained knowledge (Blind, Levels.fyi, Glassdoor, etc.)
to estimate company-specific baselines for comp, culture, trajectory,
and platform building — replacing the coarse static tier baselines with
data-informed estimates for well-known companies.

Results are cached per company name within a pipeline run so we only
call the LLM once per company, not once per job.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Reuse the same normalization as company_classifier to avoid cache misses
# when company names differ only by corporate suffixes (e.g. "Stripe, Inc." vs "stripe")
_STRIP_SUFFIXES = re.compile(
    r",?\s*\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|corporation|company|"
    r"incorporated|limited|group|holdings|technologies|technology|"
    r"software|labs|the)\b\.?",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    """Normalize a company name for cache keying."""
    name = name.strip().lower()
    name = _STRIP_SUFFIXES.sub("", name).strip()
    return re.sub(r"\s+", " ", name)

_COMPANY_INTEL_PROMPT = """\
You are a compensation and company intelligence analyst with deep knowledge of \
tech industry data from Levels.fyi, Blind, Glassdoor, and public financial reports.

Given a company name and its tier classification, estimate scoring baselines \
(0-100) for these six dimensions:

- **technical**: Engineering technical bar and depth. Consider system scale, \
technical challenges, interview difficulty, quality of engineering org, \
infrastructure complexity. FAANG/Big Tech should score high here even when \
their JDs are generic — they are known for deep technical work.
- **leadership**: Leadership and scope opportunity. Consider IC career ladders, \
tech lead paths, ability to own large projects, team building opportunities, \
mentorship culture.
- **trajectory**: Company growth trajectory and market position. Consider revenue \
growth, market cap trends, hiring velocity, product momentum, recent funding rounds.
- **comp**: Compensation competitiveness for senior-to-staff-level engineers. \
Consider base salary, RSU/equity, total comp vs market, signing bonuses.
- **culture**: Engineering culture quality. Consider work-life balance, \
remote policy, benefits, Glassdoor/Blind sentiment, tech blog presence, \
open source contributions, mentorship programs.
- **platform**: Platform building / ownership opportunity. Consider whether \
the company has greenfield projects, modernization initiatives, autonomy \
for engineers, new team formation.

Return ONLY a JSON object with these exact keys, integer values 0-100:
{"technical": N, "leadership": N, "trajectory": N, "comp": N, "culture": N, "platform": N}

Be calibrated: Google comp should be ~90, not 100. Google technical should be ~85. \
A mid-tier enterprise with mediocre Glassdoor reviews should get culture ~40, not 60.
Use your training data — do NOT default to generic tier baselines."""

_COMPANY_INTEL_USER = """\
Company: {company}
Classification: {company_type}
Additional context: {context}

Estimate the four scoring baselines (0-100 each) as JSON."""


def get_company_baselines(
    llm: Any,
    company: str,
    company_type: str,
    context: str = "",
    cache: dict[str, dict[str, float]] | None = None,
) -> dict[str, float] | None:
    """Ask the LLM for company-specific scoring baselines.

    Parameters
    ----------
    llm : LLMClient
        The configured LLM client (must have ``chat_json``).
    company : str
        Company name (e.g. "Google", "Stripe").
    company_type : str
        Tier from ``classify_company()`` (e.g. "FAANG+", "Big Tech").
    context : str
        Optional extra context (funding stage, employee count, etc.).
    cache : dict, optional
        Mutable dict for per-run caching. Pass the same dict across calls.

    Returns
    -------
    dict with keys "trajectory", "comp", "culture", "platform" (0-100 each),
    or None if the LLM is unavailable or fails.
    """
    if not llm or not llm.is_configured:
        return None

    if not company or not company.strip():
        return None

    # Cache hit — same company already scored this run
    normalized = _normalize(company)
    if not normalized:
        return None
    if cache is not None and normalized in cache:
        return cache[normalized]

    user_msg = _COMPANY_INTEL_USER.format(
        company=company,
        company_type=company_type,
        context=context or "none",
    )

    result = llm.chat_json(_COMPANY_INTEL_PROMPT, user_msg)
    if not result:
        return None

    # Validate and clamp
    baselines: dict[str, float] = {}
    for key in ("technical", "leadership", "trajectory", "comp", "culture", "platform"):
        val = result.get(key)
        if val is None:
            continue  # tolerate missing keys (backward compat with cached results)
        baselines[key] = max(0.0, min(float(val), 100.0))
    if not baselines:
        return None

    if cache is not None:
        cache[normalized] = baselines

    logger.debug("LLM company baselines for %s (%s): %s", company, company_type, baselines)
    return baselines
