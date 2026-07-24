"""One-time versioned repair that backfills pay the improved parser can read.

Career rows saved before the parser learned single stated figures
("$130,000/year") and the 'USD'/'US$' ISO forms show "reward not stated"
although the pay sits in the description. The repair re-runs the same extractor
a fresh pull uses over rows with no pay at all, fills salary_min/max (+ currency,
period, annualized) with salary_source='parsed_from_description', and never
overwrites a value the scraper already reported. Follows the description_reclean
pattern: versioned marker in data_repairs, one transaction, per-row failures
skipped, runs from _migrate_db.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from job_finder.models import database
from job_finder.models.database import ApplicationRecord


def _insert(**fields) -> int:
    defaults = {
        "job_title": "Data Engineer",
        "company": "Acme",
        "vertical": "career",
    }
    defaults.update(fields)
    session = database.get_session()
    try:
        record = ApplicationRecord(**defaults)
        session.add(record)
        session.commit()
        return record.id
    finally:
        database._close_session()


def _row(row_id: int) -> ApplicationRecord:
    session = database.get_session()
    try:
        record = session.get(ApplicationRecord, row_id)
        session.expunge(record)
        return record
    finally:
        database._close_session()


class SalaryRepairTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "job_tracker.db")
        database.init_db(self.db_path)

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def _repair(self, **kwargs) -> int:
        from job_finder.models import maintenance

        return maintenance.repair_salaries(database._engine, **kwargs)

    def test_backfills_single_stated_figure(self) -> None:
        rid = _insert(description="This role pays $130,000/year.")
        filled = self._repair()
        self.assertEqual(filled, 1)
        row = _row(rid)
        self.assertEqual(row.salary_min, 130000.0)
        self.assertIsNone(row.salary_max)
        self.assertEqual(row.salary_period, "annual")
        self.assertEqual(row.salary_min_annualized, 130000.0)
        self.assertEqual(row.salary_source, "parsed_from_description")

    def test_backfills_iso_form_range(self) -> None:
        rid = _insert(description="Compensation is USD 140,000 - 180,000 per year.")
        self._repair()
        row = _row(rid)
        self.assertEqual((row.salary_min, row.salary_max), (140000.0, 180000.0))
        self.assertEqual(row.salary_currency, "USD")

    def test_never_overwrites_reported_pay(self) -> None:
        rid = _insert(
            salary_min=150000.0,
            salary_max=200000.0,
            salary_source="reported",
            description="Some other number like $90,000/year appears here.",
        )
        filled = self._repair()
        self.assertEqual(filled, 0)
        row = _row(rid)
        self.assertEqual((row.salary_min, row.salary_max), (150000.0, 200000.0))
        self.assertEqual(row.salary_source, "reported")

    def test_leaves_genuinely_unstated_rows(self) -> None:
        rid = _insert(description="Join a great team of 150 engineers.")
        filled = self._repair()
        self.assertEqual(filled, 0)
        self.assertIsNone(_row(rid).salary_min)

    def test_skips_side_quest_rows(self) -> None:
        rid = _insert(vertical="study", description="Earn $120,000/year for this.")
        self._repair()
        self.assertIsNone(_row(rid).salary_min)

    def test_version_marker_makes_rerun_a_noop(self) -> None:
        _insert(description="Base salary is $145,000/year.")
        self.assertEqual(self._repair(), 1)
        # Second launch: the marker skips the scan even though a match exists.
        _insert(description="Base salary is $155,000/year.")
        self.assertEqual(self._repair(), 0)
        # Forced re-run only fills the still-unfilled row, not the first again.
        self.assertEqual(self._repair(force=True), 1)


if __name__ == "__main__":
    unittest.main()
