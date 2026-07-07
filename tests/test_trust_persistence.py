"""Persistence tests for the true post date (trust & freshness / ghost-job defense).

date_posted + date_confidence must survive the DB write (they were previously
dropped), backfill onto re-scrape when a better date arrives, and never
downgrade a known date back to a guess.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class TrustPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="lb-trust-test-")
        self.db_path = os.path.join(self.tempdir, "job_tracker.db")
        self._orig_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
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
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _save(self, **kw):
        base = dict(
            job_title="Senior Data Engineer", company="Acme",
            job_url=kw.pop("job_url", "https://apply.workable.com/j/ABC"),
            source="workable",
        )
        base.update(kw)
        return self.db_mod.save_application(**base)

    def test_date_posted_is_persisted(self) -> None:
        rec = self._save(date_posted="2026-06-01", date_confidence="exact")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.date_posted, "2026-06-01")
        self.assertEqual(rec.date_confidence, "exact")

    def test_missing_upgrades_to_exact_on_rescrape(self) -> None:
        r1 = self._save(date_posted="", date_confidence="missing")
        self.assertEqual(r1.date_confidence, "missing")
        # Re-scrape same URL, now with a verifiable date → should adopt it.
        r2 = self._save(date_posted="2026-06-15", date_confidence="exact")
        self.assertEqual(r2.id, r1.id)   # same record (dedup by URL)
        self.assertEqual(r2.date_posted, "2026-06-15")
        self.assertEqual(r2.date_confidence, "exact")

    def test_exact_is_not_downgraded_to_missing(self) -> None:
        r1 = self._save(date_posted="2026-06-01", date_confidence="exact")
        r2 = self._save(date_posted="", date_confidence="missing")
        self.assertEqual(r2.id, r1.id)
        self.assertEqual(r2.date_posted, "2026-06-01")   # unchanged
        self.assertEqual(r2.date_confidence, "exact")

    def test_empty_record_backfills_on_rescrape(self) -> None:
        # Simulate a pre-feature record: no date at all.
        r1 = self._save(date_posted=None, date_confidence=None)
        self.assertIn(r1.date_confidence, ("", None))
        r2 = self._save(date_posted="2026-06-20", date_confidence="fuzzy")
        self.assertEqual(r2.date_posted, "2026-06-20")
        self.assertEqual(r2.date_confidence, "fuzzy")

    def test_serializer_exposes_trust_fields(self) -> None:
        rec = self._save(
            job_url="https://apply.workable.com/j/DEF",
            date_posted="2026-06-01", date_confidence="exact",
        )
        try:
            from app.api.applications import _to_response
        except Exception:
            self.skipTest("backend app not importable in this env")
        resp = _to_response(rec)
        self.assertEqual(resp.date_posted, "2026-06-01")
        self.assertTrue(resp.direct_from_company)   # workable is a direct source

    def test_serializer_engine_source_not_direct(self) -> None:
        rec = self._save(
            job_url="https://linkedin.com/jobs/view/123",
            source="linkedin", date_posted="2026-06-01", date_confidence="exact",
        )
        try:
            from app.api.applications import _to_response
        except Exception:
            self.skipTest("backend app not importable in this env")
        resp = _to_response(rec)
        self.assertFalse(resp.direct_from_company)


if __name__ == "__main__":
    unittest.main()
