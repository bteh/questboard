"""Tests for scoring — include_equity and min_acceptable_tc."""
from __future__ import annotations

import unittest

from job_finder.scoring.core import score_job_basic
from job_finder.scoring.dimensions import score_career_progression


class IncludeEquityTest(unittest.TestCase):
    """Issue #2: include_equity setting exists but never affects scoring."""

    _JD_WITH_EQUITY = (
        "We offer equity, RSU packages, stock options, signing bonus, "
        "competitive compensation, and total compensation well above market."
    )
    _RESUME = "Experienced data engineer with 8 years of SQL and Python."

    def test_equity_signals_boost_comp_when_enabled(self) -> None:
        cfg_on = {"compensation": {"include_equity": True}}
        result_on = score_job_basic(
            self._JD_WITH_EQUITY, self._RESUME, config=cfg_on,
        )
        cfg_off = {"compensation": {"include_equity": False}}
        result_off = score_job_basic(
            self._JD_WITH_EQUITY, self._RESUME, config=cfg_off,
        )
        self.assertGreater(
            result_on["comp_potential_score"],
            result_off["comp_potential_score"],
            "Comp score should be higher when include_equity is true and "
            "equity signals are present in the JD.",
        )

    def test_equity_false_excludes_equity_signals(self) -> None:
        """When include_equity is false, a JD that ONLY has equity signals
        should get a lower comp score than a JD with salary signals."""
        jd_equity_only = "We offer equity, RSU, stock options to all employees."
        jd_salary_only = "Salary range $200,000 - $300,000."
        cfg_off = {"compensation": {"include_equity": False}}

        result_equity = score_job_basic(
            jd_equity_only, self._RESUME,
            config=cfg_off,
        )
        result_salary = score_job_basic(
            jd_salary_only, self._RESUME,
            salary_max=300_000,
            config=cfg_off,
        )
        self.assertGreater(
            result_salary["comp_potential_score"],
            result_equity["comp_potential_score"],
            "With include_equity=false, equity-only JD should not score high on comp.",
        )


class MinAcceptableTCTest(unittest.TestCase):
    """Issue #3: min_acceptable_tc saved to config but never used."""

    def test_penalty_when_salary_below_min_acceptable(self) -> None:
        cfg = {
            "career_baseline": {
                "current_title": "senior software engineer",
                "current_tc": 150_000,
                "min_acceptable_tc": 180_000,
            },
        }
        # salary_max 120K is below both current_tc and min_acceptable_tc
        score_low = score_career_progression(
            "Software Engineer", "Build systems", None, 120_000, cfg,
        )
        # salary_max 200K is above min_acceptable_tc
        score_high = score_career_progression(
            "Software Engineer", "Build systems", None, 200_000, cfg,
        )
        self.assertGreater(
            score_high, score_low,
            "Score should be lower when salary_max < min_acceptable_tc.",
        )

    def test_penalty_applied_for_below_min_but_above_current(self) -> None:
        """Salary above current_tc but below min_acceptable_tc should
        still incur the min_acceptable_tc penalty."""
        cfg = {
            "career_baseline": {
                "current_title": "software engineer",
                "current_tc": 100_000,
                "min_acceptable_tc": 200_000,
            },
        }
        # 150K > current_tc (100K) so comp upgrade fires (+20)
        # BUT 150K < min_acceptable_tc (200K) so should still get penalized
        score_mid = score_career_progression(
            "Senior Software Engineer", "Build things", None, 150_000, cfg,
        )
        # 250K > min_acceptable_tc — no penalty, and comp upgrade fires
        score_high = score_career_progression(
            "Senior Software Engineer", "Build things", None, 250_000, cfg,
        )
        self.assertGreater(
            score_high, score_mid,
            "Salary above current_tc but below min_acceptable_tc should "
            "still be penalized relative to salary above min_acceptable_tc.",
        )


if __name__ == "__main__":
    unittest.main()
