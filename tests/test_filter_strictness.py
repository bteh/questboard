"""Contract tests for the filter-strictness preset system.

The user gets very few jobs because hardcoded filter knobs in pipeline.py
narrow the result set silently (salary flex 0.85, level tolerances 1.5/2.0,
``include_founding=True``, ``all_significant`` role matching). These tests
pin the new behavior:

1. ``filters.strictness`` resolves to a preset; missing config defaults to
   ``loose`` (the widest net).
2. Explicit per-key overrides win over the preset.
3. Unknown strictness values fall back to ``loose`` (typo safety).
4. ``_match_roles`` honors the ``match_mode`` and ``include_founding`` kwargs.
5. ``_filter_jobs_by_level`` honors the resolved tolerances.
6. ``_job_salary_passes`` uses the salary_flex from the resolved settings.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class FilterPresetResolutionTest(unittest.TestCase):
    """``_resolve_filter_settings`` materializes the preset + overrides."""

    def setUp(self) -> None:
        from job_finder.pipeline import _resolve_filter_settings

        self.resolve = _resolve_filter_settings

    def test_empty_config_defaults_to_balanced(self) -> None:
        result = self.resolve({})
        self.assertEqual(result["strictness"], "balanced")
        self.assertEqual(result["salary_flex"], 0.85)
        self.assertEqual(result["role_match_mode"], "all_significant")
        self.assertTrue(result["include_founding_titles"])

    def test_none_config_defaults_to_balanced(self) -> None:
        self.assertEqual(self.resolve(None)["strictness"], "balanced")

    def test_strict_preset_applies(self) -> None:
        result = self.resolve({"filters": {"strictness": "strict"}})
        self.assertEqual(result["salary_flex"], 1.00)
        self.assertEqual(result["level_tolerance_senior"], 1.0)
        self.assertEqual(result["level_tolerance_junior"], 1.0)
        self.assertFalse(result["include_founding_titles"])
        self.assertEqual(result["role_match_mode"], "exact")

    def test_balanced_preset_applies(self) -> None:
        result = self.resolve({"filters": {"strictness": "balanced"}})
        self.assertEqual(result["salary_flex"], 0.85)
        self.assertEqual(result["role_match_mode"], "all_significant")

    def test_explicit_key_overrides_preset(self) -> None:
        result = self.resolve({"filters": {"strictness": "strict", "salary_flex": 0.5}})
        # Preset is strict but the user explicitly overrode salary_flex
        self.assertEqual(result["salary_flex"], 0.5)
        # Other strict-preset values still apply
        self.assertEqual(result["role_match_mode"], "exact")

    def test_unknown_strictness_falls_back_to_balanced(self) -> None:
        # Typo in YAML must never silently disable filtering
        result = self.resolve({"filters": {"strictness": "lol"}})
        self.assertEqual(result["strictness"], "balanced")
        self.assertEqual(result["salary_flex"], 0.85)


class MatchRolesModeTest(unittest.TestCase):
    """``_match_roles`` branches on ``match_mode``."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers._utils import _match_roles

        self.match = _match_roles

    def test_exact_substring_passes_all_modes(self) -> None:
        for mode in ("exact", "all_significant", "any_word"):
            with self.subTest(mode=mode):
                self.assertTrue(
                    self.match("Senior Data Engineer", ["data engineer"], match_mode=mode),
                    f"Substring should match in {mode} mode",
                )

    def test_any_word_matches_single_overlap(self) -> None:
        # any_word matches on a single shared DOMAIN word: "Marketing Lead"
        # shares "marketing" with role "Marketing Coordinator". (A shared
        # *generic* word like "coordinator" alone is no longer enough — that
        # was the false-positive bug.)
        self.assertTrue(
            self.match("Marketing Lead", ["Marketing Coordinator"], match_mode="any_word"),
        )

    def test_any_word_rejects_generic_only_overlap(self) -> None:
        # "Senior Coordinator" shares only the generic word "coordinator" with
        # "Marketing Coordinator" — no domain word, so any_word rejects it.
        self.assertFalse(
            self.match(
                "Senior Coordinator",
                ["Marketing Coordinator"],
                match_mode="any_word",
                include_founding=False,
            ),
        )

    def test_all_significant_rejects_single_overlap(self) -> None:
        # "Senior Coordinator" doesn't have "marketing", so all-significant fails
        self.assertFalse(
            self.match(
                "Senior Coordinator",
                ["Marketing Coordinator"],
                match_mode="all_significant",
                include_founding=False,
            ),
        )

    def test_exact_rejects_word_overlap_without_substring(self) -> None:
        # No exact substring match; "engineer" alone shouldn't be enough
        self.assertFalse(
            self.match(
                "Senior Reliability Engineer",
                ["Data Engineer"],
                match_mode="exact",
                include_founding=False,
            ),
        )

    def test_include_founding_titles_false_rejects_mts(self) -> None:
        # "MTS II" is a founding/early-startup title that gets bypassed when
        # include_founding=True (the default). Strict mode disables this.
        self.assertTrue(
            self.match("MTS II", ["Backend Engineer"], match_mode="any_word", include_founding=True),
        )
        self.assertFalse(
            self.match("MTS II", ["Backend Engineer"], match_mode="exact", include_founding=False),
        )

    def test_empty_roles_passes_everything(self) -> None:
        # No target roles configured → no filtering at all
        self.assertTrue(self.match("Anything", [], match_mode="exact"))
        self.assertTrue(self.match("Anything", None, match_mode="exact"))


class LevelToleranceTest(unittest.TestCase):
    """``_filter_jobs_by_level`` honors the resolved level tolerances."""

    def setUp(self) -> None:
        from job_finder.pipeline import _filter_jobs_by_level, _resolve_filter_settings

        self.filter = _filter_jobs_by_level
        self.resolve = _resolve_filter_settings

    def _jobs(self, *titles: str) -> list[dict]:
        return [{"title": title} for title in titles]

    def test_loose_keeps_jobs_strict_drops_them_senior_user(self) -> None:
        # User: senior (current_level=3). Job: "Junior Engineer" → level 1.
        # Gap = 3 - 1 = 2.
        # Loose tolerance_senior=2.5 → cutoff = 3 - 2.5 = 0.5; 1 >= 0.5 ✓ keeps.
        # Strict tolerance_senior=1.0 → cutoff = 3 - 1.0 = 2.0; 1 >= 2.0 ✗ drops.
        jobs = self._jobs("Junior Engineer")
        career = {"current_title": "Senior Engineer", "current_level": "senior"}

        loose = self.filter(jobs, career, filters=self.resolve({"filters": {"strictness": "loose"}}))
        strict = self.filter(jobs, career, filters=self.resolve({"filters": {"strictness": "strict"}}))

        self.assertEqual(len(loose), 1, "Loose should keep the junior-level job")
        self.assertEqual(len(strict), 0, "Strict should drop the junior-level job for a senior user")

    def test_no_career_baseline_skips_filter(self) -> None:
        # Empty career_baseline → filter is a no-op regardless of strictness
        jobs = self._jobs("Junior Coder", "Director of Engineering")
        result = self.filter(jobs, {}, filters=self.resolve({"filters": {"strictness": "strict"}}))
        self.assertEqual(len(result), 2)


class SalaryFlexTest(unittest.TestCase):
    """The ``salary_flex`` multiplier from settings controls the floor."""

    def setUp(self) -> None:
        from job_finder.pipeline import _job_salary_passes, _resolve_filter_settings

        self.passes = _job_salary_passes
        self.resolve = _resolve_filter_settings

    def test_loose_70pct_floor_passes_a_75pct_job(self) -> None:
        # User floor = 100k. Loose multiplier 0.70 → hard_floor = 70k.
        # Job paying 75k → passes.
        settings = self.resolve({"filters": {"strictness": "loose"}})
        hard_floor = 100_000 * settings["salary_flex"]
        self.assertTrue(self.passes({"salary_max": 75_000}, hard_floor))

    def test_strict_100pct_floor_rejects_a_75pct_job(self) -> None:
        settings = self.resolve({"filters": {"strictness": "strict"}})
        hard_floor = 100_000 * settings["salary_flex"]
        self.assertFalse(self.passes({"salary_max": 75_000}, hard_floor))

    def test_explicit_flex_override_wins(self) -> None:
        settings = self.resolve({
            "filters": {"strictness": "strict", "salary_flex": 0.5},
        })
        hard_floor = 100_000 * settings["salary_flex"]
        # 60k passes with flex 0.5 (hard_floor 50k) but would fail under strict's 100k
        self.assertTrue(self.passes({"salary_max": 60_000}, hard_floor))

    def test_no_salary_data_always_passes(self) -> None:
        # Documented invariant — unknown salary never gets filtered out
        self.assertTrue(self.passes({}, 200_000))


if __name__ == "__main__":
    unittest.main()
