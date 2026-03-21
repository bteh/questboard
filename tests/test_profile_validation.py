"""Tests for Pydantic-based YAML profile validation (Issue #5)."""
from __future__ import annotations

import os
import unittest

import yaml


# Path to the default profile used in production
_PROFILES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "src",
    "job_finder",
    "config",
    "profiles",
)


class TestProfileValidation(unittest.TestCase):
    """Validate that the profile schema catches misconfigurations."""

    # ------------------------------------------------------------------
    # 1. A real starter profile (default.yaml) passes validation
    # ------------------------------------------------------------------
    def test_valid_profile_passes(self) -> None:
        from job_finder.config.profile_schema import validate_profile_safe

        default_path = os.path.join(_PROFILES_DIR, "default.yaml")
        with open(default_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        profile, errors = validate_profile_safe(raw)
        self.assertIsNotNone(profile, f"Valid profile should parse; errors: {errors}")
        self.assertEqual(errors, [])

    # ------------------------------------------------------------------
    # 2. Starter profiles may omit target_roles until resume analysis/manual setup
    # ------------------------------------------------------------------
    def test_missing_target_roles_defaults_to_empty_list(self) -> None:
        from job_finder.config.profile_schema import validate_profile_safe

        profile, errors = validate_profile_safe({})
        self.assertIsNotNone(profile, f"Starter profiles should parse; errors: {errors}")
        self.assertEqual(profile.target_roles, [])
        self.assertEqual(errors, [])

    # ------------------------------------------------------------------
    # 3. Scoring weights that don't sum to ~1.0 should produce a warning
    # ------------------------------------------------------------------
    def test_invalid_weight_sum_warns(self) -> None:
        from job_finder.config.profile_schema import validate_profile_safe

        cfg = {
            "target_roles": ["software engineer"],
            "scoring": {
                "technical_skills": 0.50,
                "leadership_signal": 0.50,
                "comp_potential": 0.50,
                "platform_building": 0.50,
                "company_trajectory": 0.50,
                "culture_fit": 0.50,
                "career_progression": 0.50,
            },
        }
        profile, errors = validate_profile_safe(cfg)
        # Should still parse (it's a warning, not a hard failure) but
        # the errors list should contain a weight-sum warning.
        self.assertTrue(
            any("sum" in e.lower() or "weight" in e.lower() for e in errors),
            f"Expected weight-sum warning, got: {errors}",
        )

    # ------------------------------------------------------------------
    # 4. Negative compensation values should fail
    # ------------------------------------------------------------------
    def test_negative_compensation_fails(self) -> None:
        from job_finder.config.profile_schema import validate_profile_safe

        cfg = {
            "target_roles": ["nurse practitioner"],
            "compensation": {
                "min_base": -1,
                "target_total_comp": 100000,
                "include_equity": False,
            },
        }
        profile, errors = validate_profile_safe(cfg)
        self.assertIsNone(profile)
        self.assertTrue(
            any("min_base" in e.lower() or "negative" in e.lower() for e in errors),
            f"Expected min_base / negative error, got: {errors}",
        )

    # ------------------------------------------------------------------
    # 5. Minimal profile (just target_roles) should work with defaults
    # ------------------------------------------------------------------
    def test_partial_profile_uses_defaults(self) -> None:
        from job_finder.config.profile_schema import validate_profile_safe

        cfg = {"target_roles": ["marketing manager"]}
        profile, errors = validate_profile_safe(cfg)
        self.assertIsNotNone(profile, f"Minimal profile should work; errors: {errors}")
        self.assertEqual(errors, [])
        # Defaults should be populated
        self.assertEqual(profile.target_roles, ["marketing manager"])
        self.assertIsNone(profile.keywords)
        self.assertIsNone(profile.career_baseline)
        self.assertIsNone(profile.compensation)

    # ------------------------------------------------------------------
    # 6. validate_profile (raising variant) still raises on structurally bad input
    # ------------------------------------------------------------------
    def test_validate_profile_raises_on_bad_input(self) -> None:
        from job_finder.config.profile_schema import validate_profile

        with self.assertRaises(Exception):
            validate_profile({"target_roles": "marketing manager"})

    # ------------------------------------------------------------------
    # 7. Template profile is a valid blank starter profile
    # ------------------------------------------------------------------
    def test_template_profile_structure(self) -> None:
        """Template profile should parse as a blank starter profile."""
        from job_finder.config.profile_schema import validate_profile_safe

        template_path = os.path.join(_PROFILES_DIR, "_template.yaml")
        with open(template_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        profile, errors = validate_profile_safe(raw)
        self.assertIsNotNone(profile, f"Template should parse; errors: {errors}")
        self.assertEqual(profile.target_roles, [])
        self.assertEqual(errors, [])

    # ------------------------------------------------------------------
    # 8. Legacy list-based current_level values are normalized to strings
    # ------------------------------------------------------------------
    def test_current_level_list_is_normalized(self) -> None:
        from job_finder.config.profile_schema import validate_profile_safe

        cfg = {
            "career_baseline": {
                "current_level": ["senior"],
            },
        }
        profile, errors = validate_profile_safe(cfg)
        self.assertIsNotNone(profile, f"Profile should parse; errors: {errors}")
        self.assertEqual(profile.career_baseline.current_level, "senior")


if __name__ == "__main__":
    unittest.main()
