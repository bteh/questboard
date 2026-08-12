"""Salary preference must actually filter.

Dormant in three ways before this: (1) the UI hard-floor was written to
career_baseline.min_acceptable_tc but the filter read compensation.* (dead
key — the control did nothing); (2) salary_period was never populated so
hourly/monthly listings flowed through as if their raw number were annual;
(3) the career-progression scorer compared raw salary against annualized comp.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.pipeline import _job_salary_passes, _resolve_salary_floor
from job_finder.scoring.dimensions import score_career_progression
from job_finder.scoring.helpers import annualize_amount


class SalaryFloorResolutionTest(unittest.TestCase):
    def test_floor_from_career_baseline_the_ui_path(self) -> None:
        # The UI writes the hard floor here; the filter must read it (was the dead key).
        self.assertEqual(_resolve_salary_floor({"career_baseline": {"min_acceptable_tc": 150000}}), 150000)

    def test_floor_from_compensation(self) -> None:
        self.assertEqual(_resolve_salary_floor({"compensation": {"min_acceptable_tc": 150000}}), 150000)

    def test_floor_min_base_fallback(self) -> None:
        self.assertEqual(_resolve_salary_floor({"compensation": {"min_base": 120000}}), 120000)

    def test_no_floor_configured(self) -> None:
        self.assertEqual(_resolve_salary_floor({}), 0)

    def test_floor_annualized_from_period(self) -> None:
        # An hourly floor should annualize.
        floor = _resolve_salary_floor({"compensation": {"min_base": 60, "pay_period": "hourly"}})
        self.assertEqual(floor, 60 * 2080)


class JobSalaryPassesTest(unittest.TestCase):
    def test_annualized_above_floor_passes(self) -> None:
        self.assertTrue(_job_salary_passes({"salary_max_annualized": 166400}, 127500))

    def test_annual_below_floor_drops(self) -> None:
        self.assertFalse(_job_salary_passes({"salary_max": 90000}, 127500))

    def test_unknown_salary_passes(self) -> None:
        self.assertTrue(_job_salary_passes({}, 127500))

    def test_hourly_annualized_passes(self) -> None:
        # 80/hr -> 166,400/yr clears a 127.5k floor (raw 80 would wrongly fail).
        job = {"salary_max": 80, "salary_max_annualized": annualize_amount(80, "hourly")}
        self.assertTrue(_job_salary_passes(job, 127500))

    def test_same_currency_below_floor_drops(self) -> None:
        self.assertFalse(_job_salary_passes(
            {"salary_max": 90_000, "salary_currency": "USD"},
            127_500,
            "USD",
        ))

    def test_different_currency_is_not_compared_as_usd(self) -> None:
        self.assertTrue(_job_salary_passes(
            {"salary_max": 90_000, "salary_currency": "EUR"},
            127_500,
            "USD",
        ))

    def test_missing_currency_is_not_assumed(self) -> None:
        self.assertTrue(_job_salary_passes({"salary_max": 90_000}, 127_500, "USD"))


class JobSpyPeriodTest(unittest.TestCase):
    def test_jobspy_interval_populates_period_and_annualized(self) -> None:
        from job_finder.tools import job_search_tool

        def fake_scrape_jobs(**kwargs):
            return pd.DataFrame([{
                "site": "indeed", "title": "Engineer", "company_name": "Acme",
                "location": "Remote", "is_remote": True, "job_url": "https://x",
                "description": "", "date_posted": "2026-05-01",
                "min_amount": 60, "max_amount": 80, "interval": "hourly", "currency": "USD",
            }])

        job_search_tool.reset_circuit()
        with patch.dict(sys.modules, {"jobspy": MagicMock(scrape_jobs=fake_scrape_jobs)}):
            jobs = job_search_tool.search_jobs(search_term="engineer", boards=["indeed"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["salary_period"], "hourly")
        self.assertEqual(jobs[0]["salary_max_annualized"], 80 * 2080)
        self.assertEqual(jobs[0]["salary_currency"], "USD")


class CareerProgressionAnnualizeTest(unittest.TestCase):
    def test_hourly_job_not_penalized_as_step_down(self) -> None:
        cfg = {"career_baseline": {"current_tc": 150000}, "compensation": {"pay_period": "annual"}}
        # 90/hr ~ 187k/yr: a comp UPGRADE once annualized.
        annualized = score_career_progression("Senior Engineer", "", 0, 90, cfg, salary_period="hourly")
        raw = score_career_progression("Senior Engineer", "", 0, 90, cfg, salary_period="")
        self.assertGreater(annualized, raw)


if __name__ == "__main__":
    unittest.main()
