"""Versioned repair that collapses existing cross-source duplicate rows.

Rows saved before the squashed-company dedup fix can sit on the board twice:
the same opening once from a direct ATS source and once from an aggregator,
under different URLs (the Alo "Manager of Data Engineering" pair). The repair
finds those clusters with the shared dedup key, keeps the best row (protected
statuses first, then direct source, then richness), merges pay/dates the
keeper lacked, and tombstones the losers with status='expired' plus a note.
Losers are never hard-deleted, so receipts survive.

Follows the description_reclean pattern: versioned marker in data_repairs,
one transaction, per-cluster failures skipped, runs from _migrate_db.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from job_finder.models import database
from job_finder.models.database import ApplicationRecord

_ALO_DESC = (
    "WHY JOIN ALO? Mindful movement. It's at the core of why we do what we do "
    "at ALO. Because mindful movement in the studio leads to better living. "
    "We are looking for a Manager of Data Engineering to lead our pipelines, "
    "own the lakehouse migration, and grow a team of two engineers."
)

_LONG_A = (
    "Own and scale the data platform end to end: design batch and streaming "
    "pipelines, lead the lakehouse migration, and mentor two engineers on it."
)


def _insert(**fields) -> int:
    defaults = {
        "job_title": "Manager of Data Engineering",
        "company": "Aloyoga",
        "location": "Beverly Hills, California, United States",
        "description": _ALO_DESC,
        "source": "greenhouse",
        "status": "found",
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


class DuplicateRepairTest(unittest.TestCase):
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

        return maintenance.repair_duplicates(database._engine, **kwargs)

    def test_alo_pair_collapses_direct_keeper_borrows_pay(self) -> None:
        keeper_id = _insert(
            company="Aloyoga", source="greenhouse",
            job_url="https://boards.greenhouse.io/aloyoga/jobs/6119207004",
        )
        loser_id = _insert(
            company="ALO", source="linkedin",
            location="Beverly Hills, CA",
            description=_ALO_DESC + " Plus benefits and equity for everyone.",
            job_url="https://www.linkedin.com/jobs/view/4442198160",
            salary_min=140000.0, salary_max=180000.0,
            date_posted="2026-07-17", date_confidence="exact",
        )

        self.assertEqual(self._repair(), 1)

        keeper = _row(keeper_id)
        loser = _row(loser_id)
        # direct ATS row wins and absorbs the aggregator's pay and date
        self.assertEqual(keeper.status, "found")
        self.assertEqual(keeper.salary_min, 140000.0)
        self.assertEqual(keeper.salary_max, 180000.0)
        self.assertEqual(keeper.date_posted, "2026-07-17")
        self.assertEqual(keeper.date_confidence, "exact")
        # loser is tombstoned, never deleted; its receipts survive
        self.assertEqual(loser.status, "expired")
        self.assertEqual(loser.url_status, "expired")
        self.assertIn(f"#{keeper_id}", loser.notes)
        self.assertIn("duplicate", loser.notes.lower())
        self.assertEqual(loser.job_url, "https://www.linkedin.com/jobs/view/4442198160")

    def test_clipped_row_always_wins_even_against_direct_source(self) -> None:
        direct_id = _insert(
            company="Aloyoga", source="greenhouse", status="found",
            job_url="https://boards.greenhouse.io/aloyoga/jobs/6119207004",
        )
        clipped_id = _insert(
            company="ALO", source="linkedin", status="clipped",
            location="Beverly Hills, CA",
            job_url="https://www.linkedin.com/jobs/view/4442198160",
        )

        self.assertEqual(self._repair(), 1)

        self.assertEqual(_row(clipped_id).status, "clipped")
        direct = _row(direct_id)
        self.assertEqual(direct.status, "expired")
        self.assertIn(f"#{clipped_id}", direct.notes)

    def test_two_protected_rows_both_survive_found_sibling_expires(self) -> None:
        clipped_id = _insert(status="clipped", job_url="https://a.example/1")
        applied_id = _insert(status="applied", job_url="https://a.example/2",
                             source="linkedin", company="ALO",
                             location="Beverly Hills, CA")
        found_id = _insert(status="found", job_url="https://a.example/3",
                           source="indeed", company="Alo Yoga",
                           location="Beverly Hills, CA")

        self.assertEqual(self._repair(), 1)

        self.assertEqual(_row(clipped_id).status, "clipped")
        self.assertEqual(_row(applied_id).status, "applied")
        self.assertEqual(_row(found_id).status, "expired")

    def test_different_cities_survive(self) -> None:
        a = _insert(company="Gamma", job_title="Software Engineer",
                    location="Austin, TX", description=_LONG_A,
                    job_url="https://g.example/1", source="indeed")
        b = _insert(company="Gamma", job_title="Software Engineer",
                    location="Seattle, WA", description=_LONG_A,
                    job_url="https://g.example/2", source="linkedin")

        self.assertEqual(self._repair(), 0)
        self.assertEqual(_row(a).status, "found")
        self.assertEqual(_row(b).status, "found")

    def test_quest_rows_never_collapse(self) -> None:
        a = _insert(vertical="study", company="UCLA Lab",
                    job_title="Paid Sleep Study", location="Los Angeles, CA",
                    job_url="https://q.example/1", source="clinicaltrials")
        b = _insert(vertical="study", company="UCLA Lab",
                    job_title="Paid Sleep Study", location="Los Angeles, CA",
                    job_url="https://q.example/2", source="focusgroups_org")

        self.assertEqual(self._repair(), 0)
        self.assertEqual(_row(a).status, "found")
        self.assertEqual(_row(b).status, "found")

    def test_scopes_never_cross_merge(self) -> None:
        # same posting saved under two different profiles = two boards;
        # the repair must not reach across them
        a = _insert(profile="default", job_url="https://s.example/1")
        b = _insert(profile="workspace", source="linkedin", company="ALO",
                    location="Beverly Hills, CA", job_url="https://s.example/2")

        self.assertEqual(self._repair(), 0)
        self.assertEqual(_row(a).status, "found")
        self.assertEqual(_row(b).status, "found")

    def test_second_run_is_noop_and_marker_prevents_rescan(self) -> None:
        from job_finder.models import maintenance

        _insert(job_url="https://m.example/1")
        _insert(source="linkedin", company="ALO", location="Beverly Hills, CA",
                job_url="https://m.example/2")
        self.assertEqual(self._repair(), 1)

        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT version FROM data_repairs WHERE name = ?",
                (maintenance.DUPLICATE_REPAIR_NAME,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], maintenance.DUPLICATE_REPAIR_VERSION)

        def _boom(*_args):  # pragma: no cover - must never be called
            raise AssertionError("marker did not prevent a rescan")

        with patch.object(maintenance, "_scan_and_collapse_duplicates", _boom):
            self.assertEqual(self._repair(), 0)

    def test_repair_does_not_reshuffle_updated_at(self) -> None:
        keeper_id = _insert(job_url="https://t.example/1")
        loser_id = _insert(source="linkedin", company="ALO",
                           location="Beverly Hills, CA",
                           job_url="https://t.example/2",
                           salary_min=100000.0)
        before = {rid: _row(rid).updated_at for rid in (keeper_id, loser_id)}

        self.assertEqual(self._repair(), 1)

        for rid in (keeper_id, loser_id):
            self.assertEqual(_row(rid).updated_at, before[rid])

    def test_startup_hook_collapses_on_init_db(self) -> None:
        keeper_id = _insert(job_url="https://h.example/1")
        loser_id = _insert(source="linkedin", company="ALO",
                           location="Beverly Hills, CA",
                           job_url="https://h.example/2")
        # Same startup path the dev backend and desktop sidecar use:
        # init_db -> _migrate_db -> run_startup_repairs.
        database.init_db(self.db_path)

        self.assertEqual(_row(keeper_id).status, "found")
        self.assertEqual(_row(loser_id).status, "expired")


if __name__ == "__main__":
    unittest.main()
