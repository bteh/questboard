"""One-time versioned repair for relative-prose and epoch date_posted rows.

Rows scraped before the freshness-anchor fix store the source's words
("Reposted 3 Days Ago", "Yesterday") or a bare unix epoch as date_posted.
Prose is only meaningful relative to scrape time, so the repair converts it
to ISO computed as date_found minus the stated offset (confidence 'fuzzy'),
converts bare 10-13 digit epochs to the ISO instant they encode (confidence
kept), and leaves everything else byte-identical. Follows the
description_reclean pattern: versioned marker in data_repairs, one
transaction, per-row failures skipped, runs from _migrate_db.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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


def _iso(moment: datetime) -> str:
    """The repair's output shape: naive-UTC ISO, second precision."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class DateRepairTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "job_tracker.db")
        database.init_db(self.db_path)
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def _repair(self, **kwargs) -> int:
        from job_finder.models import maintenance

        return maintenance.repair_dates(database._engine, **kwargs)

    def test_prose_rows_convert_to_anchored_iso_with_fuzzy_confidence(self) -> None:
        found = self.now - timedelta(days=6, hours=12)
        days_id = _insert(
            job_url="https://example.com/a",
            date_posted="Reposted 3 Days Ago",
            date_confidence="fuzzy",
            date_found=found,
        )
        hours_id = _insert(
            job_url="https://example.com/b",
            date_posted="Posted 20 Hours Ago",
            date_confidence="missing",
            date_found=found,
        )
        yesterday_id = _insert(
            job_url="https://example.com/c",
            date_posted="Yesterday",
            date_confidence="missing",
            date_found=found,
        )
        today_id = _insert(
            job_url="https://example.com/d",
            date_posted="Posted Today",
            date_confidence="",
            date_found=found,
        )

        self.assertEqual(self._repair(), 4)

        days = _row(days_id)
        self.assertEqual(days.date_posted, _iso(found - timedelta(days=3)))
        self.assertEqual(days.date_confidence, "fuzzy")
        hours = _row(hours_id)
        self.assertEqual(hours.date_posted, _iso(found - timedelta(hours=20)))
        self.assertEqual(hours.date_confidence, "fuzzy")
        yesterday = _row(yesterday_id)
        self.assertEqual(yesterday.date_posted, _iso(found - timedelta(days=1)))
        self.assertEqual(yesterday.date_confidence, "fuzzy")
        today = _row(today_id)
        self.assertEqual(today.date_posted, _iso(found))
        self.assertEqual(today.date_confidence, "fuzzy")

    def test_epoch_rows_convert_and_keep_their_confidence(self) -> None:
        posted = self.now - timedelta(days=2)
        secs_id = _insert(
            job_url="https://example.com/e",
            date_posted=str(int(posted.timestamp())),
            date_confidence="exact",
            date_found=self.now,
        )
        millis_id = _insert(
            job_url="https://example.com/f",
            date_posted=str(int(posted.timestamp()) * 1000),
            date_confidence="",
            date_found=self.now,
        )
        # An epoch needs no date_found anchor: it encodes its own instant.
        anchorless_id = _insert(
            job_url="https://example.com/g",
            date_posted=str(int(posted.timestamp())),
            date_confidence="exact",
        )
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE applications SET date_found = NULL WHERE id = ?",
                (anchorless_id,),
            )

        self.assertEqual(self._repair(), 3)

        expected = _iso(datetime.fromtimestamp(int(posted.timestamp()), tz=timezone.utc))
        secs = _row(secs_id)
        self.assertEqual(secs.date_posted, expected)
        self.assertEqual(secs.date_confidence, "exact")
        millis = _row(millis_id)
        self.assertEqual(millis.date_posted, expected)
        self.assertEqual(millis.date_confidence, "")
        self.assertEqual(_row(anchorless_id).date_posted, expected)

    def test_untouchable_rows_stay_byte_identical(self) -> None:
        iso_value = (self.now - timedelta(days=2)).isoformat()
        iso_id = _insert(
            job_url="https://example.com/h",
            date_posted=iso_value,
            date_confidence="exact",
            date_found=self.now,
        )
        empty_id = _insert(job_url="https://example.com/i", date_posted="")
        rfc_id = _insert(
            job_url="https://example.com/j",
            date_posted="Wed, 15 Jul 2026 20:56:13 +0000",
            date_confidence="exact",
            date_found=self.now,
        )
        # Prose with NO usable date_found cannot be anchored; leave it alone.
        anchorless_id = _insert(
            job_url="https://example.com/k",
            date_posted="Reposted 3 Days Ago",
            date_confidence="fuzzy",
        )
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE applications SET date_found = NULL WHERE id = ?",
                (anchorless_id,),
            )

        self.assertEqual(self._repair(), 0)

        self.assertEqual(_row(iso_id).date_posted, iso_value)
        self.assertEqual(_row(empty_id).date_posted, "")
        self.assertEqual(_row(rfc_id).date_posted, "Wed, 15 Jul 2026 20:56:13 +0000")
        anchorless = _row(anchorless_id)
        self.assertEqual(anchorless.date_posted, "Reposted 3 Days Ago")
        self.assertEqual(anchorless.date_confidence, "fuzzy")

    def test_repair_never_bumps_updated_at(self) -> None:
        row_id = _insert(
            job_url="https://example.com/l",
            date_posted="Reposted 3 Days Ago",
            date_confidence="fuzzy",
            date_found=self.now - timedelta(days=6),
        )
        before = _row(row_id).updated_at

        self.assertEqual(self._repair(), 1)

        self.assertEqual(_row(row_id).updated_at, before)

    def test_second_run_is_noop_and_marker_prevents_rescan(self) -> None:
        from job_finder.models import maintenance

        row_id = _insert(
            job_url="https://example.com/m",
            date_posted="Reposted 3 Days Ago",
            date_confidence="fuzzy",
            date_found=self.now - timedelta(days=6),
        )
        self.assertEqual(self._repair(), 1)
        converted = _row(row_id).date_posted

        # The version marker is recorded ...
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT version FROM data_repairs WHERE name = ?",
                (maintenance.DATE_REPAIR_NAME,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], maintenance.DATE_REPAIR_VERSION)

        # ... and it short-circuits the second run before any row is read.
        def _boom(conn, available):  # pragma: no cover - must never be called
            raise AssertionError("marker did not prevent a rescan")

        with patch.object(maintenance, "_scan_and_repair_dates", _boom):
            self.assertEqual(self._repair(), 0)

        # A forced re-scan converts nothing: ISO output no longer matches
        # the prose or epoch shapes, so the repair is a fixed point.
        self.assertEqual(self._repair(force=True), 0)
        self.assertEqual(_row(row_id).date_posted, converted)

    def test_one_broken_row_never_aborts_the_repair(self) -> None:
        broken_id = _insert(
            job_url="https://example.com/n",
            date_posted="Reposted 3 Days Ago",
            date_confidence="fuzzy",
        )
        with sqlite3.connect(self.db_path) as con:
            con.execute(
                "UPDATE applications SET date_found = 'not a timestamp' WHERE id = ?",
                (broken_id,),
            )
        good_id = _insert(
            job_url="https://example.com/o",
            date_posted="Yesterday",
            date_confidence="missing",
            date_found=self.now,
        )

        self.assertEqual(self._repair(), 1)

        # Raw read-back: the ORM cannot parse the corrupt date_found.
        with sqlite3.connect(self.db_path) as con:
            (broken_posted,) = con.execute(
                "SELECT date_posted FROM applications WHERE id = ?", (broken_id,)
            ).fetchone()
        self.assertEqual(broken_posted, "Reposted 3 Days Ago")
        self.assertEqual(
            _row(good_id).date_posted, _iso(self.now - timedelta(days=1))
        )

    def test_startup_hook_runs_the_date_repair(self) -> None:
        from job_finder.models import maintenance

        row_id = _insert(
            job_url="https://example.com/p",
            date_posted="Reposted 2 Days Ago",
            date_confidence="fuzzy",
            date_found=self.now - timedelta(days=5),
        )
        # Fresh DB: _migrate_db returned before the hook during init, so no
        # marker exists yet and the hook has real work to do here.
        maintenance.run_startup_repairs(database._engine)

        self.assertEqual(
            _row(row_id).date_posted,
            _iso(self.now - timedelta(days=5) - timedelta(days=2)),
        )


if __name__ == "__main__":
    unittest.main()
