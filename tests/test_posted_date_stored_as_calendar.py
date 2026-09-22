"""date_posted is stored in ONE shape: naive-UTC ISO 8601 at second precision.

Real case (Brian, Sep 22 2026): the Find Work board's "posted last 7 days"
filter hid 15 of the 44 postings from that week. board_filter_conditions
compares applications.date_posted as TEXT against "2026-09-15T17:00:00"
strings, which only works when the stored value is ISO. Scrapers stored
whatever the source gave them:

- Himalayas, Getro, CryptoJobsList, Lever, Arbeitnow, Ashby, Workday: epoch
  seconds as a string ("1789542352", Himalayas "Senior Manager, Data
  Engineering" at Zscaler, found Sep 15 2026). "1789..." sorts below
  "2026..." so the row vanished. 1,600 live rows looked like this.
- We Work Remotely: RFC 2822 ("Thu, 03 Sep 2026 10:00:00 +0000"), which
  _parse_posted_date did not read either.
- Greenhouse sometimes: ISO with an offset ("2026-09-15T15:07:18-04:00",
  Appian "Lead Applied AI Engineer"), read as if UTC; two rows fell off the
  boundary.

The class fix: normalize_posted_date is the single choke point. The database
write path calls it, a versioned repair calls it for rows already stored,
and _parse_posted_date reads every shape the normalizer does so the Python
freshness gate and the SQL filter agree.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from app.services.application_service import board_filter_conditions  # noqa: E402
from job_finder.models import database  # noqa: E402
from job_finder.models.database import ApplicationRecord  # noqa: E402
from job_finder.tools.scrapers._utils import (  # noqa: E402
    _parse_posted_date,
    normalize_posted_date,
)

STORED = "%Y-%m-%dT%H:%M:%S"


def _stored(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(STORED)


def _epoch_seconds(days_ago: int) -> str:
    return str(int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp()))


class NormalizerTest(unittest.TestCase):
    def test_epoch_seconds_string_becomes_utc_iso(self) -> None:
        self.assertEqual(normalize_posted_date("1789542352"), "2026-09-16T07:05:52")

    def test_epoch_seconds_int_and_milliseconds_become_utc_iso(self) -> None:
        self.assertEqual(normalize_posted_date(1789542352), "2026-09-16T07:05:52")
        self.assertEqual(normalize_posted_date("1789542352000"), "2026-09-16T07:05:52")
        self.assertEqual(normalize_posted_date(1749340800000), "2025-06-08T00:00:00")

    def test_rfc_2822_becomes_utc_iso(self) -> None:
        self.assertEqual(
            normalize_posted_date("Thu, 03 Sep 2026 10:00:00 +0000"),
            "2026-09-03T10:00:00",
        )
        self.assertEqual(
            normalize_posted_date("Mon, 15 Jun 2026 20:07:47 -0400"),
            "2026-06-16T00:07:47",
        )

    def test_iso_with_offset_is_converted_to_utc(self) -> None:
        self.assertEqual(
            normalize_posted_date("2026-09-15T15:07:18-04:00"), "2026-09-15T19:07:18"
        )
        self.assertEqual(
            normalize_posted_date("2026-06-09T06:47:41.476Z"), "2026-06-09T06:47:41"
        )
        self.assertEqual(
            normalize_posted_date("2026-06-09T06:47:41.476+00:00"), "2026-06-09T06:47:41"
        )

    def test_canonical_value_is_a_fixed_point(self) -> None:
        self.assertEqual(normalize_posted_date("2026-09-15T17:00:00"), "2026-09-15T17:00:00")

    def test_date_only_stays_date_only(self) -> None:
        # A bare date cannot prove a 24-hour window; board_filter_conditions
        # and the prose repair rely on that, so no midnight is invented.
        self.assertEqual(normalize_posted_date("2026-09-15"), "2026-09-15")

    def test_free_text_and_empty_are_unchanged(self) -> None:
        for raw in ("Reposted 9 Days Ago", "8 Days Ago", "Posted 30+ Days Ago", "", "recently"):
            self.assertEqual(normalize_posted_date(raw), raw)
        self.assertEqual(normalize_posted_date(None), "")

    def test_parse_posted_date_reads_rfc_2822_so_both_helpers_agree(self) -> None:
        parsed = _parse_posted_date("Thu, 03 Sep 2026 10:00:00 +0000")
        self.assertEqual(parsed, datetime(2026, 9, 3, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(
            _stored(parsed), normalize_posted_date("Thu, 03 Sep 2026 10:00:00 +0000")
        )
        self.assertIsNone(_parse_posted_date("Reposted 9 Days Ago"))


class _TempDbTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "job_tracker.db")
        database.init_db(self.db_path)
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def _insert_raw(self, **fields) -> int:
        """A row exactly as a pre-fix scraper run left it (no normalizing)."""
        defaults = {"job_title": "Data Engineer", "company": "Acme", "vertical": "career"}
        defaults.update(fields)
        session = database.get_session()
        try:
            record = ApplicationRecord(**defaults)
            session.add(record)
            session.commit()
            return record.id
        finally:
            database._close_session()

    def _row(self, row_id: int) -> ApplicationRecord:
        session = database.get_session()
        try:
            record = session.get(ApplicationRecord, row_id)
            session.expunge(record)
            return record
        finally:
            database._close_session()

    def _titles_posted_within(self, days: int) -> set[str]:
        session = database.get_session()
        try:
            rows = (
                session.query(ApplicationRecord)
                .filter(*board_filter_conditions(ApplicationRecord, posted_within_days=days))
                .all()
            )
            return {r.job_title for r in rows}
        finally:
            database._close_session()


class WritePathTest(_TempDbTest):
    def test_new_row_stores_the_calendar_shape(self) -> None:
        posted = self.now - timedelta(days=5)
        record = database.save_application(
            job_title="Senior Manager, Data Engineering",
            company="Zscaler",
            job_url="https://himalayas.app/companies/zscaler/jobs/1",
            source="himalayas",
            date_posted=str(int(posted.timestamp())),
            date_confidence="exact",
        )
        self.assertEqual(self._row(record.id).date_posted, _stored(posted))

    def test_new_row_from_rfc_2822_and_offset_iso_stores_the_calendar_shape(self) -> None:
        wwr = database.save_application(
            job_title="Staff Data Engineer",
            company="Acme",
            job_url="https://weworkremotely.com/remote-jobs/acme-staff",
            source="weworkremotely",
            date_posted="Thu, 03 Sep 2026 10:00:00 +0000",
            date_confidence="exact",
        )
        gh = database.save_application(
            job_title="Lead Applied AI Engineer",
            company="Appian",
            job_url="https://boards.greenhouse.io/appian/jobs/1",
            source="greenhouse",
            date_posted="2026-09-15T15:07:18-04:00",
            date_confidence="exact",
        )
        self.assertEqual(self._row(wwr.id).date_posted, "2026-09-03T10:00:00")
        self.assertEqual(self._row(gh.id).date_posted, "2026-09-15T19:07:18")

    def test_rescrape_of_the_same_url_stores_the_calendar_shape(self) -> None:
        url = "https://himalayas.app/companies/zscaler/jobs/2"
        first = database.save_application(
            job_title="Data Platform Lead", company="Zscaler", job_url=url,
            source="himalayas", date_posted="", date_confidence="missing",
        )
        posted = self.now - timedelta(days=3)
        database.save_application(
            job_title="Data Platform Lead", company="Zscaler", job_url=url,
            source="himalayas", date_posted=str(int(posted.timestamp())),
            date_confidence="exact",
        )
        self.assertEqual(self._row(first.id).date_posted, _stored(posted))

    def test_cross_source_merge_stores_the_calendar_shape(self) -> None:
        older = self.now - timedelta(days=10)
        newer = self.now - timedelta(days=4)
        keeper = database.save_application(
            job_title="Analytics Engineer", company="Zscaler", location="Remote",
            job_url="https://example.com/direct/1", source="greenhouse",
            date_posted=_stored(older), date_confidence="exact",
        )
        database.save_application(
            job_title="Analytics Engineer", company="Zscaler", location="Remote",
            job_url="https://himalayas.app/companies/zscaler/jobs/3", source="himalayas",
            date_posted=str(int(newer.timestamp())), date_confidence="exact",
        )
        self.assertEqual(self._row(keeper.id).date_posted, _stored(newer))


class SqlFilterTest(_TempDbTest):
    def test_seven_day_filter_finds_a_himalayas_row_saved_this_week(self) -> None:
        database.save_application(
            job_title="Fresh epoch", company="Zscaler",
            job_url="https://himalayas.app/companies/zscaler/jobs/fresh",
            source="himalayas", date_posted=_epoch_seconds(5), date_confidence="exact",
        )
        database.save_application(
            job_title="Stale epoch", company="Zscaler",
            job_url="https://himalayas.app/companies/zscaler/jobs/stale",
            source="himalayas", date_posted=_epoch_seconds(20), date_confidence="exact",
        )
        self.assertEqual(self._titles_posted_within(7), {"Fresh epoch"})

    def test_seven_day_filter_finds_a_stored_epoch_row_only_after_the_repair(self) -> None:
        from job_finder.models.posted_date_repair import repair_posted_dates

        self._insert_raw(
            job_title="Fresh epoch", job_url="https://example.com/fresh",
            date_posted=_epoch_seconds(5), date_confidence="exact",
        )
        self._insert_raw(
            job_title="Stale epoch", job_url="https://example.com/stale",
            date_posted=_epoch_seconds(20), date_confidence="exact",
        )
        self.assertEqual(self._titles_posted_within(7), set())

        repair_posted_dates(database._engine)

        self.assertEqual(self._titles_posted_within(7), {"Fresh epoch"})


class RepairTest(_TempDbTest):
    def _repair(self, **kwargs) -> int:
        from job_finder.models.posted_date_repair import repair_posted_dates

        return repair_posted_dates(database._engine, **kwargs)

    def test_epoch_rfc_and_offset_rows_are_rewritten_in_place(self) -> None:
        posted = self.now - timedelta(days=5)
        secs = self._insert_raw(
            job_url="https://example.com/a", date_posted=str(int(posted.timestamp())),
            date_confidence="exact",
        )
        millis = self._insert_raw(
            job_url="https://example.com/b", date_posted=str(int(posted.timestamp()) * 1000),
            date_confidence="",
        )
        rfc = self._insert_raw(
            job_url="https://example.com/c", date_posted="Thu, 03 Sep 2026 10:00:00 +0000",
            date_confidence="missing",
        )
        offset = self._insert_raw(
            job_url="https://example.com/d", date_posted="2026-09-15T15:07:18-04:00",
            date_confidence="exact",
        )
        zulu = self._insert_raw(
            job_url="https://example.com/e", date_posted="2026-06-09T06:47:41.476Z",
            date_confidence="fuzzy",
        )
        before = self._row(secs).updated_at

        self.assertEqual(self._repair(), 5)

        self.assertEqual(self._row(secs).date_posted, _stored(posted))
        self.assertEqual(self._row(secs).date_confidence, "exact")
        self.assertEqual(self._row(millis).date_posted, _stored(posted))
        self.assertEqual(self._row(millis).date_confidence, "")
        self.assertEqual(self._row(rfc).date_posted, "2026-09-03T10:00:00")
        self.assertEqual(self._row(rfc).date_confidence, "exact")
        self.assertEqual(self._row(offset).date_posted, "2026-09-15T19:07:18")
        self.assertEqual(self._row(zulu).date_posted, "2026-06-09T06:47:41")
        self.assertEqual(self._row(zulu).date_confidence, "fuzzy")
        self.assertEqual(self._row(secs).updated_at, before)

    def test_missing_confidence_is_rejudged_only_when_the_date_now_parses(self) -> None:
        """We Work Remotely, Sep 22 2026: 100 of its 103 rows carried
        date_confidence "missing" because the old parser could not read RFC
        2822, so the 7-day filter kept hiding them even with the date fixed.
        A row the pipeline marked missing for a date that still does not
        parse stays missing; a fuzzy row stays fuzzy."""
        rfc = self._insert_raw(
            job_url="https://example.com/wwr", date_posted="Thu, 03 Sep 2026 10:00:00 +0000",
            date_confidence="missing",
        )
        prose = self._insert_raw(
            job_url="https://example.com/workday", date_posted="Posted 9 Days Ago",
            date_confidence="missing",
        )
        fuzzy = self._insert_raw(
            job_url="https://example.com/fuzzy", date_posted="2026-09-15T19:07:18",
            date_confidence="fuzzy",
        )

        self.assertEqual(self._repair(), 1)

        self.assertEqual(self._row(rfc).date_confidence, "exact")
        self.assertEqual(self._row(prose).date_posted, "Posted 9 Days Ago")
        self.assertEqual(self._row(prose).date_confidence, "missing")
        self.assertEqual(self._row(fuzzy).date_confidence, "fuzzy")

    def test_free_text_date_only_canonical_and_empty_rows_stay_byte_identical(self) -> None:
        untouched = {
            "https://example.com/f": "Reposted 9 Days Ago",
            "https://example.com/g": "Posted 30+ Days Ago",
            "https://example.com/h": "2026-09-15",
            "https://example.com/i": "2026-09-15T17:00:00",
            "https://example.com/j": "",
        }
        ids = {
            url: self._insert_raw(job_url=url, date_posted=value, date_confidence="fuzzy")
            for url, value in untouched.items()
        }

        self.assertEqual(self._repair(), 0)

        for url, value in untouched.items():
            row = self._row(ids[url])
            self.assertEqual(row.date_posted, value)
            self.assertEqual(row.date_confidence, "fuzzy")

    def test_marker_is_recorded_and_a_second_run_touches_nothing(self) -> None:
        from job_finder.models import posted_date_repair

        row_id = self._insert_raw(
            job_url="https://example.com/k", date_posted="1789542352", date_confidence="exact",
        )
        self.assertEqual(self._repair(), 1)
        converted = self._row(row_id).date_posted

        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT version FROM data_repairs WHERE name = ?",
                (posted_date_repair.POSTED_DATE_REPAIR_NAME,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], posted_date_repair.POSTED_DATE_REPAIR_VERSION)

        def _boom(conn):  # pragma: no cover - must never be called
            raise AssertionError("marker did not prevent a rescan")

        with patch.object(posted_date_repair, "_scan", _boom):
            self.assertEqual(self._repair(), 0)

        self.assertEqual(self._repair(force=True), 0)
        self.assertEqual(self._row(row_id).date_posted, converted)

    def test_one_broken_row_never_aborts_the_repair(self) -> None:
        from job_finder.models import posted_date_repair

        broken = self._insert_raw(
            job_url="https://example.com/l", date_posted="1789542351", date_confidence="exact",
        )
        good = self._insert_raw(
            job_url="https://example.com/m", date_posted="1789542352", date_confidence="exact",
        )
        real = posted_date_repair.normalize_posted_date

        def _flaky(raw: object) -> str:
            if raw == "1789542351":
                raise RuntimeError("simulated per-row failure")
            return real(raw)

        with patch.object(posted_date_repair, "normalize_posted_date", _flaky):
            self.assertEqual(self._repair(), 1)

        self.assertEqual(self._row(broken).date_posted, "1789542351")
        self.assertEqual(self._row(good).date_posted, "2026-09-16T07:05:52")

    def test_startup_hook_runs_this_repair_after_the_prose_repair(self) -> None:
        from job_finder.models import maintenance, posted_date_repair

        rfc = self._insert_raw(
            job_url="https://example.com/n", date_posted="Thu, 03 Sep 2026 10:00:00 +0000",
            date_confidence="exact",
        )
        order: list[str] = []
        real_dates = maintenance.repair_dates
        real_posted = posted_date_repair.repair_posted_dates

        def _dates(engine, **kw):
            order.append("repair_dates")
            return real_dates(engine, **kw)

        def _posted(engine, **kw):
            order.append("repair_posted_dates")
            return real_posted(engine, **kw)

        with patch.object(maintenance, "repair_dates", _dates), patch.object(
            posted_date_repair, "repair_posted_dates", _posted
        ):
            maintenance.run_startup_repairs(database._engine)

        self.assertEqual(self._row(rfc).date_posted, "2026-09-03T10:00:00")
        self.assertEqual(
            order.index("repair_posted_dates"), order.index("repair_dates") + 1
        )


if __name__ == "__main__":
    unittest.main()
