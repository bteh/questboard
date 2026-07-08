"""Dead/expired postings should be hidden from listings by default — and only
TRULY dead URLs (404/410) should be marked dead, not bot-blocked HEADs (403/
405/timeouts), which would otherwise hide good jobs.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for p in (BACKEND_PATH, SRC_PATH):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class _Resp:
    def __init__(self, code):
        self.status_code = code


class DeadLinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = {k: os.environ.get(k) for k in
                      ["DATA_DIR", "HOSTED_MODE", "MANAGE_SCHEMA_ON_STARTUP", "DATABASE_URL"]}
        self.temp_dir = tempfile.mkdtemp(prefix="questboard-deadlink-")
        self.db_path = os.path.join(self.temp_dir, "job_tracker.db")
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        for name in list(sys.modules):
            if name == "app" or name.startswith("app.") or name.startswith("job_finder.models"):
                sys.modules.pop(name, None)
        self.db_mod = importlib.import_module("app.models.database")
        self.db_mod.init_db(self.db_path)
        self.svc = importlib.import_module("app.services.application_service")
        self.AR = importlib.import_module("app.models.application").ApplicationRecord

    def tearDown(self) -> None:
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _session(self):
        return self.db_mod._SessionLocal()

    def _add(self, title, status="unknown", url="https://x/1"):
        db = self._session()
        try:
            db.add(self.AR(job_title=title, company="Acme", job_url=url, url_status=status))
            db.commit()
        finally:
            db.close()

    def test_listings_exclude_dead_by_default(self) -> None:
        self._add("Alive Engineer", status="alive", url="https://x/alive")
        self._add("Dead Engineer", status="dead", url="https://x/dead")
        self._add("Unknown Engineer", status="unknown", url="https://x/unknown")
        db = self._session()
        try:
            items, _ = self.svc.get_applications(db, exclude_dead=True)
            titles = {i.job_title for i in items}
            self.assertIn("Alive Engineer", titles)
            self.assertIn("Unknown Engineer", titles)
            self.assertNotIn("Dead Engineer", titles)
            # opt-in to show all
            items_all, _ = self.svc.get_applications(db, exclude_dead=False)
            self.assertIn("Dead Engineer", {i.job_title for i in items_all})
        finally:
            db.close()

    def test_check_urls_only_404_410_marks_dead(self) -> None:
        self._add("Gone", url="https://x/404")
        self._add("Live", url="https://x/200")
        self._add("Blocked", url="https://x/403")
        self._add("Slow", url="https://x/timeout")

        def fake_head(url, **kwargs):
            if url.endswith("/404"):
                return _Resp(404)
            if url.endswith("/200"):
                return _Resp(200)
            if url.endswith("/403"):
                return _Resp(403)
            raise TimeoutError("slow")

        with patch("requests.head", side_effect=fake_head):
            db = self._session()
            try:
                self.svc.check_urls(db)
            finally:
                db.close()

        db = self._session()
        try:
            by_title = {r.job_title: r.url_status for r in db.query(self.AR).all()}
        finally:
            db.close()
        self.assertEqual(by_title["Gone"], "dead")
        self.assertEqual(by_title["Live"], "alive")
        self.assertEqual(by_title["Blocked"], "unknown")   # 403 bot-block ≠ dead
        self.assertEqual(by_title["Slow"], "unknown")      # timeout ≠ dead


if __name__ == "__main__":
    unittest.main()
