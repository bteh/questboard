"""Hosted mode: one shared felt, personal logs, clone-on-touch.

Quest rows live in ONE shared pool (workspace_id NULL) that the scheduler
sweeps; every visitor's board reads it. Career rows stay per-workspace
(your resume drove that search). Touching a shared quest row clones it
into your workspace first, so your log is yours and the shared row stays
pristine for everyone else. The ops surfaces are admin-only here.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

TEST_JWT_SECRET = "test-supabase-secret-with-32-bytes"
ADMIN_EMAIL = "ops@example.com"


class HostedSharedBoardTest(unittest.TestCase):
    ENV_KEYS = [
        "DATA_DIR", "WORKSPACE_STORAGE_DIR", "HOSTED_MODE", "SESSION_SECURE_COOKIES",
        "ALLOW_RUNTIME_LLM_CONFIG", "HOSTED_ALLOW_WORKSPACE_LLM_CONFIG",
        "HOSTED_PLATFORM_MANAGED_AI", "SUPABASE_URL", "SUPABASE_JWT_SECRET",
        "SUPABASE_JWT_AUDIENCE", "MANAGE_SCHEMA_ON_STARTUP", "DATABASE_URL",
        "APP_RELEASE", "ADMIN_EMAILS", "SCHEDULER_ENABLED",
    ]

    def setUp(self) -> None:
        self._original_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        self.temp_dir = tempfile.mkdtemp(prefix="questboard-shared-board-test-")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.db_path = os.path.join(self.data_dir, "job_tracker.db")
        os.makedirs(self.data_dir, exist_ok=True)
        os.environ.update({
            "DATA_DIR": self.data_dir,
            "WORKSPACE_STORAGE_DIR": os.path.join(self.temp_dir, "workspaces"),
            "HOSTED_MODE": "true",
            "SESSION_SECURE_COOKIES": "false",
            "ALLOW_RUNTIME_LLM_CONFIG": "false",
            "HOSTED_ALLOW_WORKSPACE_LLM_CONFIG": "false",
            "HOSTED_PLATFORM_MANAGED_AI": "true",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_JWT_SECRET": TEST_JWT_SECRET,
            "SUPABASE_JWT_AUDIENCE": "authenticated",
            "MANAGE_SCHEMA_ON_STARTUP": "true",
            "DATABASE_URL": f"sqlite:///{self.db_path}",
            "APP_RELEASE": "test-release",
            "ADMIN_EMAILS": ADMIN_EMAIL,
            "SCHEDULER_ENABLED": "false",
        })

        for module_name in list(sys.modules):
            if (
                module_name == "app"
                or module_name.startswith("app.")
                or module_name == "job_finder.models"
                or module_name.startswith("job_finder.models.")
            ):
                sys.modules.pop(module_name, None)
        backend_db = importlib.import_module("app.models.database")
        backend_db.init_db(self.db_path)
        self.jf_db = importlib.import_module("job_finder.models.database")
        self.jf_db.init_db(self.db_path)
        app_main = importlib.import_module("app.main")

        self.client = TestClient(app_main.app)
        self.addCleanup(self.client.close)

    def tearDown(self) -> None:
        if self.jf_db._SessionLocal is not None:
            self.jf_db._SessionLocal.remove()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _headers(self, *, user_id: str, email: str) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "email": email,
            "email_confirmed_at": now.isoformat(),
            "app_metadata": {"provider": "google"},
            "user_metadata": {"full_name": email.split("@")[0]},
        }
        token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def _seed_shared_quest(self, title: str, url: str) -> int:
        """A quest row in the shared pool, as a scheduler sweep would write it."""
        self.jf_db.save_application(
            job_title=title, company="Fixture Bank", job_url=url,
            location="nationwide", vertical="house",
        )
        session = self.jf_db.get_session()
        try:
            row = (
                session.query(self.jf_db.ApplicationRecord)
                .filter(self.jf_db.ApplicationRecord.job_url == url)
                .one()
            )
            assert row.workspace_id is None
            return row.id
        finally:
            session.close()

    def _board(self, headers, **params):
        query = {"vertical": "house", "scope": "board", **params}
        resp = self.client.get("/api/v1/applications", params=query, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()

    # ---- the shared felt ----

    def test_every_visitor_sees_the_shared_quest_pool(self) -> None:
        self._seed_shared_quest("Fixture $200 bonus", "https://x.example/bonus1")
        a = self._headers(user_id="user-a", email="a@example.com")
        b = self._headers(user_id="user-b", email="b@example.com")

        titles_a = {r["job_title"] for r in self._board(a)["items"]}
        titles_b = {r["job_title"] for r in self._board(b)["items"]}
        self.assertIn("Fixture $200 bonus", titles_a)
        self.assertIn("Fixture $200 bonus", titles_b)

    def test_career_rows_stay_private_per_workspace(self) -> None:
        a = self._headers(user_id="user-a", email="a@example.com")
        b = self._headers(user_id="user-b", email="b@example.com")
        created = self.client.post(
            "/api/v1/applications",
            json={"job_title": "A's private job", "company": "Acme", "vertical": "career"},
            headers=a,
        )
        self.assertEqual(created.status_code, 201, created.text)

        board_a = self._board(a, vertical="career")
        board_b = self._board(b, vertical="career")
        self.assertIn("A's private job", {r["job_title"] for r in board_a["items"]})
        self.assertNotIn("A's private job", {r["job_title"] for r in board_b["items"]})

    def test_the_log_scope_hides_the_shared_pool(self) -> None:
        self._seed_shared_quest("Fixture $200 bonus", "https://x.example/bonus1")
        a = self._headers(user_id="user-a", email="a@example.com")
        log = self.client.get(
            "/api/v1/applications",
            params={"vertical": "house"},  # scope defaults to mine
            headers=a,
        ).json()
        self.assertEqual(log["total"], 0)

    # ---- clone-on-touch ----

    def test_clipping_a_shared_row_clones_it_and_leaves_the_original_pristine(self) -> None:
        shared_id = self._seed_shared_quest("Fixture $200 bonus", "https://x.example/bonus1")
        a = self._headers(user_id="user-a", email="a@example.com")
        b = self._headers(user_id="user-b", email="b@example.com")

        clipped = self.client.patch(
            f"/api/v1/applications/{shared_id}/status",
            json={"status": "clipped"},
            headers=a,
        )
        self.assertEqual(clipped.status_code, 200, clipped.text)
        copy_id = clipped.json()["id"]
        self.assertNotEqual(copy_id, shared_id)

        # A's board shows exactly one row for that URL: their clipped copy
        rows_a = self._board(a)["items"]
        mine = [r for r in rows_a if r["job_url"] == "https://x.example/bonus1"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["id"], copy_id)
        self.assertEqual(mine[0]["status"], "clipped")

        # A's log now holds the copy
        log_a = self.client.get(
            "/api/v1/applications", params={"vertical": "house"}, headers=a
        ).json()
        self.assertEqual(log_a["total"], 1)

        # B still sees the pristine shared row
        rows_b = self._board(b)["items"]
        theirs = [r for r in rows_b if r["job_url"] == "https://x.example/bonus1"]
        self.assertEqual(len(theirs), 1)
        self.assertEqual(theirs[0]["id"], shared_id)
        # pristine = the save default, untouched by A's clip
        self.assertEqual(theirs[0]["status"], "found")

    def test_touching_the_shared_id_twice_never_duplicates(self) -> None:
        shared_id = self._seed_shared_quest("Fixture $200 bonus", "https://x.example/bonus1")
        a = self._headers(user_id="user-a", email="a@example.com")

        first = self.client.patch(
            f"/api/v1/applications/{shared_id}/status",
            json={"status": "clipped"}, headers=a,
        ).json()
        # a stale client sends the SHARED id again
        second = self.client.patch(
            f"/api/v1/applications/{shared_id}/status",
            json={"status": "applied"}, headers=a,
        ).json()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["status"], "applied")
        log = self.client.get(
            "/api/v1/applications", params={"vertical": "house"}, headers=a
        ).json()
        self.assertEqual(log["total"], 1)

    def test_board_summary_counts_the_shared_pool(self) -> None:
        self._seed_shared_quest("Fixture $200 bonus", "https://x.example/bonus1")
        a = self._headers(user_id="user-a", email="a@example.com")
        summary = self.client.get("/api/v1/board/summary", headers=a)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["total"], 1)

    # ---- the board restocks itself ----

    def test_hosted_quest_refresh_is_the_schedulers_job(self) -> None:
        a = self._headers(user_id="user-a", email="a@example.com")
        resp = self.client.post(
            "/api/v1/quests/refresh", json={"verticals": ["house"]}, headers=a,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertIn("restocks itself", resp.json()["detail"])

    # ---- ops surfaces are admin-only here ----

    def test_ops_endpoints_require_an_admin(self) -> None:
        visitor = self._headers(user_id="user-a", email="a@example.com")
        admin = self._headers(user_id="ops-1", email=ADMIN_EMAIL)
        for path in ("/api/v1/scrapers/health", "/api/v1/scrapers/runs", "/api/v1/scrapers/schedule"):
            self.assertEqual(self.client.get(path, headers=visitor).status_code, 403, path)
            self.assertEqual(self.client.get(path, headers=admin).status_code, 200, path)

    def test_sources_stay_open_for_the_settings_page(self) -> None:
        visitor = self._headers(user_id="user-a", email="a@example.com")
        resp = self.client.get("/api/v1/scrapers/sources", headers=visitor)
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
