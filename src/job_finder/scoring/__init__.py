"""Job scoring package — modular, company-tier-aware keyword scoring.

Public API:
    score_job_basic()           — Main scorer (keywords + TF-IDF + tier baselines)
    get_company_baselines()     — LLM-powered per-company scoring baselines

Architecture:
    signals.py      — Keyword lists, tier baselines, level maps
    helpers.py      — keyword_score, tfidf_similarity, salary_score
    dimensions.py   — Per-dimension scoring functions (technical, leadership, …)
    company_intel.py — LLM-powered company intelligence scoring
    core.py         — Orchestrator that combines dimensions + baselines
"""

from job_finder.scoring.company_intel import get_company_baselines
from job_finder.scoring.company_intel import _normalize as normalize_company_key
from job_finder.scoring.core import score_job_basic

__all__ = ["score_job_basic", "get_company_baselines", "normalize_company_key"]
