"""Tests for _match_roles — verifying cross-profession role filtering.

Regression: non-tech roles (e.g. nursing) were seeing unrelated software jobs in
results because the broad fallback matched generic keywords ("engineer", "lead").
Fix: _match_roles only matches explicit role keywords, no broad fallback.

These tests use inline role lists (not profile files) to verify the filtering
logic works across different professions.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from job_finder.tools.scrapers._utils import _match_roles


# -- Non-tech roles (used to verify cross-profession filtering) ---------------

NURSE_ROLES = [
    "nurse practitioner",
    "family nurse practitioner",
    "nurse practitioner primary care",
    "lead nurse practitioner",
    "clinical director",
    "director of nursing",
    "nurse manager",
    "advanced practice provider",
    "APP",
    "NP",
]


class TestMatchRolesNurseProfile:
    """_match_roles must NOT let unrelated tech jobs through when nurse roles are provided."""

    def test_rejects_software_engineer(self):
        """The exact bug: 'Lead Software Engineer, Full Stack' matched via fallback."""
        assert _match_roles("Lead Software Engineer, Full Stack", NURSE_ROLES) is False

    def test_rejects_software_engineer_5(self):
        """The exact bug: 'Software Engineer 5' at Netflix matched via fallback."""
        assert _match_roles("Software Engineer 5", NURSE_ROLES) is False

    def test_rejects_senior_data_engineer(self):
        assert _match_roles("Senior Data Engineer", NURSE_ROLES) is False

    def test_rejects_staff_frontend_engineer(self):
        assert _match_roles("Staff Frontend Engineer", NURSE_ROLES) is False

    def test_rejects_product_manager(self):
        assert _match_roles("Product Manager", NURSE_ROLES) is False

    def test_rejects_data_scientist(self):
        assert _match_roles("Data Scientist", NURSE_ROLES) is False

    def test_rejects_ml_engineer(self):
        assert _match_roles("Machine Learning Engineer", NURSE_ROLES) is False

    def test_rejects_devops_engineer(self):
        assert _match_roles("DevOps Engineer", NURSE_ROLES) is False

    def test_rejects_platform_architect(self):
        assert _match_roles("Platform Architect", NURSE_ROLES) is False

    def test_accepts_nurse_practitioner(self):
        assert _match_roles("Nurse Practitioner", NURSE_ROLES) is True

    def test_accepts_family_nurse_practitioner(self):
        assert _match_roles("Family Nurse Practitioner - Primary Care", NURSE_ROLES) is True

    def test_accepts_lead_nurse_practitioner(self):
        assert _match_roles("Lead Nurse Practitioner", NURSE_ROLES) is True

    def test_accepts_clinical_director(self):
        assert _match_roles("Clinical Director - Outpatient", NURSE_ROLES) is True

    def test_accepts_director_of_nursing(self):
        assert _match_roles("Director of Nursing", NURSE_ROLES) is True

    def test_accepts_nurse_manager(self):
        assert _match_roles("Nurse Manager - ICU", NURSE_ROLES) is True

    def test_accepts_advanced_practice_provider(self):
        assert _match_roles("Advanced Practice Provider", NURSE_ROLES) is True

    def test_accepts_np_abbreviation(self):
        """NP as a role should match titles containing NP."""
        assert _match_roles("NP - Family Medicine", NURSE_ROLES) is True


# -- Default data engineer profile roles (existing behavior) ------------------

DATA_ENGINEER_ROLES = [
    "data engineer",
    "senior data engineer",
    "analytics engineer",
    "data platform engineer",
]


class TestMatchRolesDataEngineerProfile:
    """_match_roles should still work correctly for tech profiles."""

    def test_accepts_data_engineer(self):
        assert _match_roles("Data Engineer", DATA_ENGINEER_ROLES) is True

    def test_accepts_senior_data_engineer(self):
        assert _match_roles("Senior Data Engineer", DATA_ENGINEER_ROLES) is True

    def test_accepts_analytics_engineer(self):
        assert _match_roles("Analytics Engineer II", DATA_ENGINEER_ROLES) is True

    def test_rejects_nurse_practitioner(self):
        """Tech profile should not match nurse jobs."""
        assert _match_roles("Nurse Practitioner", DATA_ENGINEER_ROLES) is False

    def test_rejects_registered_nurse(self):
        assert _match_roles("Registered Nurse - ICU", DATA_ENGINEER_ROLES) is False

    def test_rejects_dental_hygienist(self):
        assert _match_roles("Dental Hygienist", DATA_ENGINEER_ROLES) is False


# -- No roles = accept everything (backward compat) --------------------------

class TestMatchRolesNoFilter:
    """When roles is None or empty, everything passes."""

    def test_none_roles_accepts_anything(self):
        assert _match_roles("Literally Anything", None) is True

    def test_empty_roles_accepts_anything(self):
        assert _match_roles("Literally Anything", []) is True


# -- AI role expansion tests ------------------------------------------------

class TestAIRoleExpansion:
    """Test that expand_roles_with_ai enriches role keywords via LLM."""

    def _make_pipeline(self, llm_response: dict | None = None):
        from job_finder.pipeline import JobFinderPipeline

        mock_llm = MagicMock()
        mock_llm.is_configured = True
        mock_llm.chat_json.return_value = llm_response

        pipeline = JobFinderPipeline.__new__(JobFinderPipeline)
        pipeline.llm = mock_llm
        pipeline.profile_name = "test"
        pipeline.config = {}
        return pipeline

    def test_expands_nurse_roles(self):
        """LLM returns related nursing keywords that get merged."""
        pipeline = self._make_pipeline({
            "expanded_keywords": ["APRN", "primary care provider", "FNP-C", "telehealth NP"]
        })
        result = pipeline.expand_roles_with_ai(["nurse practitioner", "FNP"])
        assert "nurse practitioner" in result
        assert "FNP" in result
        assert "APRN" in result
        assert "primary care provider" in result
        assert len(result) == 6  # 2 originals + 4 expansions

    def test_deduplicates_case_insensitive(self):
        """Expanded keywords that already exist (case-insensitive) are skipped."""
        pipeline = self._make_pipeline({
            "expanded_keywords": ["Nurse Practitioner", "APRN", "fnp"]
        })
        result = pipeline.expand_roles_with_ai(["nurse practitioner", "FNP"])
        # "Nurse Practitioner" and "fnp" are dupes of originals
        assert len(result) == 3  # 2 originals + 1 new (APRN)

    def test_falls_back_without_llm(self):
        """When no LLM is configured, returns original roles unchanged."""
        from job_finder.pipeline import JobFinderPipeline

        pipeline = JobFinderPipeline.__new__(JobFinderPipeline)
        pipeline.llm = None
        pipeline.profile_name = "test"
        pipeline.config = {}

        roles = ["nurse practitioner", "FNP"]
        result = pipeline.expand_roles_with_ai(roles)
        assert result is roles  # exact same object, no modification

    def test_falls_back_on_llm_error(self):
        """When LLM call fails, returns original roles."""
        pipeline = self._make_pipeline(None)  # LLM returns None
        roles = ["data engineer"]
        result = pipeline.expand_roles_with_ai(roles)
        assert result == ["data engineer"]

    def test_expanded_roles_filter_correctly(self):
        """End-to-end: AI-expanded nurse roles still reject software titles."""
        pipeline = self._make_pipeline({
            "expanded_keywords": [
                "APRN", "primary care provider", "FNP-C",
                "registered nurse", "clinical nurse specialist",
            ]
        })
        expanded = pipeline.expand_roles_with_ai(NURSE_ROLES)

        # Software titles must NOT match even with expanded keywords
        assert _match_roles("Lead Software Engineer", expanded) is False
        assert _match_roles("Software Engineer 5", expanded) is False
        assert _match_roles("Senior Data Engineer", expanded) is False

        # Nurse titles must still match
        assert _match_roles("Nurse Practitioner", expanded) is True
        assert _match_roles("APRN - Primary Care", expanded) is True
        assert _match_roles("Clinical Nurse Specialist", expanded) is True
