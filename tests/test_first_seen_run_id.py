"""Contract tests for first_seen_run_id stamping and immutability.

The application data model overwrites ``search_run_id`` to the most recent
run that re-surfaced each job. That loses the historical "which run found
this first" answer. ``first_seen_run_id`` fixes the gap — set ONCE on
initial insert, never overwritten on re-discovery.

These tests pin the invariants:

1. On first insert with a run_id, both ``search_run_id`` and
   ``first_seen_run_id`` get set to the same value.
2. On re-discovery by job_url with a different run_id, ``search_run_id``
   updates but ``first_seen_run_id`` stays unchanged.
3. On re-discovery by normalized company+title dedup, same behavior:
   ``first_seen_run_id`` is preserved.
4. The lightweight schema migration adds the column and backfills
   existing rows' ``first_seen_run_id`` from their current
   ``search_run_id`` so historical runs aren't all stamped as "new."
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class FirstSeenRunIdTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="lb-first-seen-test-")
        self.db_path = os.path.join(self.tempdir, "job_tracker.db")
        # Reset env so the modules pick up our temp DB.
        self._orig_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"

        # Force re-import so the singletons rebind to our DB.
        for mod in list(sys.modules):
            if mod == "job_finder.models" or mod.startswith("job_finder.models."):
                sys.modules.pop(mod, None)

        from job_finder.models import database as db_mod

        self.db_mod = db_mod
        db_mod.init_db(self.db_path)

    def tearDown(self) -> None:
        if self._orig_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self._orig_db_url
        import shutil

        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _save(self, **kwargs):
        defaults = dict(
            job_title="Software Engineer",
            company="ACME Corp",
            job_url="https://acme.example/jobs/1",
            source="himalayas",
            profile="default",
        )
        defaults.update(kwargs)
        return self.db_mod.save_application(**defaults)

    def test_initial_insert_stamps_first_seen_run_id_equal_to_search_run_id(self) -> None:
        record = self._save(search_run_id="run-aaa")
        self.assertEqual(record.search_run_id, "run-aaa")
        self.assertEqual(record.first_seen_run_id, "run-aaa")

    def test_rediscovery_by_url_preserves_first_seen_run_id(self) -> None:
        first = self._save(search_run_id="run-aaa")
        self.assertEqual(first.first_seen_run_id, "run-aaa")

        # Same job_url, different run_id — should resolve to the existing row,
        # bumping search_run_id but NOT first_seen_run_id.
        second = self._save(search_run_id="run-bbb")
        self.assertEqual(second.id, first.id, "Same URL should dedup to same row")
        self.assertEqual(second.search_run_id, "run-bbb")
        self.assertEqual(second.first_seen_run_id, "run-aaa")

    def test_rediscovery_by_company_title_preserves_first_seen_run_id(self) -> None:
        # Same company + title but different URLs — dedup path #2 (normalized
        # company+title) takes over.
        first = self._save(
            company="Stripe, Inc.",
            job_title="Backend Engineer",
            job_url="https://board-a.example/jobs/100",
            search_run_id="run-aaa",
        )
        second = self._save(
            company="Stripe",
            job_title="Backend Engineer",
            job_url="https://board-b.example/jobs/200",
            search_run_id="run-bbb",
        )
        self.assertEqual(second.id, first.id, "Cross-source dedup should resolve to same row")
        self.assertEqual(second.search_run_id, "run-bbb")
        self.assertEqual(second.first_seen_run_id, "run-aaa")

    def test_insert_without_run_id_leaves_first_seen_run_id_null(self) -> None:
        record = self._save(search_run_id=None)
        self.assertIsNone(record.search_run_id)
        self.assertIsNone(record.first_seen_run_id)

    def test_migration_backfills_legacy_rows(self) -> None:
        """Existing rows with search_run_id but no first_seen_run_id get backfilled."""
        import sqlalchemy as sa

        engine = self.db_mod._engine
        with engine.begin() as conn:
            # Simulate a legacy row that pre-dates the new column: drop the
            # column then re-add via the migration helper.
            cols = [
                row[1] for row in conn.execute(sa.text("PRAGMA table_info(applications)")).fetchall()
            ]
            self.assertIn("first_seen_run_id", cols, "Migration should have added the column")
            # Wipe its value to simulate an upgrade scenario.
            conn.execute(
                sa.text("UPDATE applications SET first_seen_run_id = NULL")
            )
            conn.execute(
                sa.text(
                    "INSERT INTO applications (job_title, company, job_url, source, profile, search_run_id) "
                    "VALUES ('Legacy', 'Old Corp', 'https://old.example/legacy', 'himalayas', 'default', 'legacy-run')"
                )
            )

        # Re-run the migration. It should backfill first_seen_run_id from
        # search_run_id for the legacy row.
        self.db_mod._migrate_db(engine)

        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT search_run_id, first_seen_run_id FROM applications "
                    "WHERE job_url = 'https://old.example/legacy'"
                )
            ).fetchall()
        self.assertEqual(len(rows), 1)
        search_run_id, first_seen_run_id = rows[0]
        self.assertEqual(search_run_id, "legacy-run")
        self.assertEqual(
            first_seen_run_id,
            "legacy-run",
            "Backfill should copy search_run_id into first_seen_run_id for legacy rows",
        )


if __name__ == "__main__":
    unittest.main()
