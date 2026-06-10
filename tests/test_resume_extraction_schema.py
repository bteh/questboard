"""Tests for resume extraction schema: certifications/education extraction (FIX 1),
high_comp_signals split (FIX 2), and raised suggestion caps (FIX 4).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from app.services.resume_analyzer import _EXTRACTION_PROMPT, apply_analysis_to_profile
from job_finder.config.profile_schema import validate_profile_safe


CERTS = ["RN", "FNP-C", "PMP"]
EDUCATION = [
    {"degree": "BSN", "field": "Nursing", "institution": "UCLA"},
    {"degree": "MSN", "field": "Family Practice", "institution": "Johns Hopkins"},
]


def _analysis(**overrides) -> dict:
    base = {
        "industry": "healthcare",
        "seniority": "senior",
        "current_title": "Nurse Practitioner",
        "years_experience": 8,
        "skills": ["Patient Care", "Triage"],
        "leadership_signals": ["charge nurse"],
        "suggested_target_roles": ["Nurse Practitioner"],
        "suggested_keywords": ["primary care"],
        "certifications": list(CERTS),
        "education": [dict(e) for e in EDUCATION],
        "high_comp_keywords": ["equity", "RSU", "sign-on bonus"],
        "company_tier_signals": ["Kaiser Permanente", "Mayo Clinic"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Extraction prompt schema (FIX 1 + FIX 2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field",
    ["certifications", "education", "high_comp_keywords", "company_tier_signals"],
)
def test_extraction_prompt_includes_new_fields(field: str) -> None:
    assert field in _EXTRACTION_PROMPT


# ---------------------------------------------------------------------------
# FIX 1 — certifications + education round-trip
# ---------------------------------------------------------------------------

def test_certs_and_education_roundtrip_empty_profile() -> None:
    cfg = apply_analysis_to_profile({}, _analysis())
    assert cfg["certifications"] == CERTS
    assert cfg["education"] == EDUCATION


def test_force_overwrite_true_replaces_existing_certs_and_education() -> None:
    existing = {
        "certifications": ["OLD-CERT"],
        "education": [{"degree": "AA", "field": "General", "institution": "CC"}],
    }
    cfg = apply_analysis_to_profile(existing, _analysis(), force_overwrite=True)
    assert cfg["certifications"] == CERTS
    assert cfg["education"] == EDUCATION


def test_force_overwrite_false_preserves_existing_certs_and_education() -> None:
    existing = {
        "certifications": ["OLD-CERT"],
        "education": [{"degree": "AA", "field": "General", "institution": "CC"}],
    }
    cfg = apply_analysis_to_profile(existing, _analysis(), force_overwrite=False)
    assert cfg["certifications"] == ["OLD-CERT"]
    assert cfg["education"] == [{"degree": "AA", "field": "General", "institution": "CC"}]


def test_certifications_do_not_count_against_skill_cap() -> None:
    skills = [f"Skill {i}" for i in range(25)]
    cfg = apply_analysis_to_profile({}, _analysis(skills=skills))
    technical = cfg["keywords"]["technical"]
    assert len(technical) == 20
    assert technical == skills[:20]
    assert cfg["certifications"] == CERTS
    for cert in CERTS:
        assert cert not in technical


# ---------------------------------------------------------------------------
# FIX 2 — high_comp_signals split
# ---------------------------------------------------------------------------

def test_new_style_fields_route_to_correct_profile_keys() -> None:
    cfg = apply_analysis_to_profile({}, _analysis())
    assert cfg["keywords"]["high_comp_signals"] == ["equity", "RSU", "sign-on bonus"]
    assert cfg["keywords"]["company_tier_signals"] == ["Kaiser Permanente", "Mayo Clinic"]


def test_company_names_never_land_in_high_comp_signals() -> None:
    cfg = apply_analysis_to_profile({}, _analysis())
    for company in ("Kaiser Permanente", "Mayo Clinic"):
        assert company not in cfg["keywords"]["high_comp_signals"]


def test_old_style_high_comp_signals_still_accepted() -> None:
    analysis = _analysis()
    del analysis["high_comp_keywords"]
    del analysis["company_tier_signals"]
    analysis["high_comp_signals"] = ["equity", "bonus", "Apple"]
    cfg = apply_analysis_to_profile({}, analysis)
    assert cfg["keywords"]["high_comp_signals"] == ["equity", "bonus", "Apple"]
    assert "company_tier_signals" not in cfg["keywords"]


def test_force_overwrite_semantics_for_company_tier_signals() -> None:
    existing = {"keywords": {"company_tier_signals": ["OldCo"]}}
    kept = apply_analysis_to_profile(existing, _analysis(), force_overwrite=False)
    assert kept["keywords"]["company_tier_signals"] == ["OldCo"]
    replaced = apply_analysis_to_profile(existing, _analysis(), force_overwrite=True)
    assert replaced["keywords"]["company_tier_signals"] == ["Kaiser Permanente", "Mayo Clinic"]


# ---------------------------------------------------------------------------
# FIX 4 — raised caps for suggested roles/keywords
# ---------------------------------------------------------------------------

def test_suggested_roles_cap_raised_to_25() -> None:
    roles = [f"Role {i}" for i in range(30)]
    cfg = apply_analysis_to_profile({}, _analysis(suggested_target_roles=roles))
    assert cfg["target_roles"] == roles[:25]


def test_suggested_keywords_cap_raised_to_20() -> None:
    keywords = [f"keyword {i}" for i in range(30)]
    cfg = apply_analysis_to_profile({}, _analysis(suggested_keywords=keywords))
    assert cfg["keyword_searches"] == keywords[:20]


# ---------------------------------------------------------------------------
# Profile schema validation accepts the new fields
# ---------------------------------------------------------------------------

def test_profile_schema_validates_new_fields() -> None:
    cfg = apply_analysis_to_profile({}, _analysis())
    profile, errors = validate_profile_safe(cfg)
    assert profile is not None, errors
    assert [c for c in profile.certifications or []] == CERTS
    edu = [e.model_dump() for e in profile.education or []]
    assert [{k: d[k] for k in ("degree", "field", "institution")} for d in edu] == EDUCATION
    assert profile.keywords is not None
    assert profile.keywords.company_tier_signals == ["Kaiser Permanente", "Mayo Clinic"]


def test_education_entries_normalized_to_plain_dicts() -> None:
    messy = _analysis(
        education=[
            {"degree": " BSN ", "field": "Nursing", "institution": " UCLA "},
            {"degree": " BSN ", "field": "nursing", "institution": "ucla"},  # dup
            "not-a-dict",
            {"degree": "", "field": "", "institution": ""},  # empty
        ]
    )
    cfg = apply_analysis_to_profile({}, messy)
    assert cfg["education"] == [{"degree": "BSN", "field": "Nursing", "institution": "UCLA"}]
