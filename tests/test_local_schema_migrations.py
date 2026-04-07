from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
if BACKEND_PATH in sys.path:
    sys.path.remove(BACKEND_PATH)
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class LocalSchemaMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {key: os.environ.get(key) for key in [
            "DATA_DIR",
            "WORKSPACE_STORAGE_DIR",
            "HOSTED_MODE",
            "MANAGE_SCHEMA_ON_STARTUP",
            "DATABASE_URL",
            "EMBEDDED_SCHEDULER_ENABLED",
        ]}
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-local-migrate-")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.workspace_dir = os.path.join(self.temp_dir, "workspaces")
        self.db_path = os.path.join(self.data_dir, "job_tracker.db")
        os.makedirs(self.data_dir, exist_ok=True)
        os.environ["DATA_DIR"] = self.data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = self.workspace_dir
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ.pop("DATABASE_URL", None)
        os.environ["EMBEDDED_SCHEDULER_ENABLED"] = "false"

        self._create_legacy_database()

        for module_name in list(sys.modules):
            if (
                module_name == "app"
                or module_name.startswith("app.")
                or module_name == "job_finder.models"
                or module_name.startswith("job_finder.models.")
            ):
                sys.modules.pop(module_name, None)

        self.backend_db = importlib.import_module("app.models.database")
        self.backend_db.init_db(self.db_path)
        self.app_main = importlib.import_module("app.main")
        self.scheduler_start = patch.object(self.app_main, "start_scheduler", lambda: None)
        self.scheduler_stop = patch.object(self.app_main, "stop_scheduler", lambda: None)
        self.scheduler_start.start()
        self.scheduler_stop.start()
        self.addCleanup(self.scheduler_start.stop)
        self.addCleanup(self.scheduler_stop.stop)

        self.client = TestClient(self.app_main.app)
        self.addCleanup(self.client.close)

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_legacy_database(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_url TEXT
                );

                CREATE TABLE workspaces (
                    id TEXT PRIMARY KEY,
                    mode TEXT DEFAULT 'personal',
                    created_at TEXT,
                    updated_at TEXT,
                    last_active_at TEXT,
                    expires_at TEXT
                );

                CREATE TABLE workspace_resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT,
                    original_filename TEXT DEFAULT '',
                    stored_filename TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    text_path TEXT DEFAULT '',
                    mime_type TEXT DEFAULT 'application/pdf',
                    file_size INTEGER DEFAULT 0,
                    parse_status TEXT DEFAULT 'missing',
                    parse_warning TEXT DEFAULT '',
                    extracted_text TEXT DEFAULT '',
                    llm_summary TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE TABLE workspace_search_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id TEXT,
                    run_id TEXT,
                    status TEXT DEFAULT 'pending',
                    mode TEXT DEFAULT 'search_score',
                    snapshot_json TEXT DEFAULT '{}',
                    jobs_found INTEGER DEFAULT 0,
                    jobs_scored INTEGER DEFAULT 0,
                    strong_matches INTEGER DEFAULT 0,
                    error TEXT DEFAULT '',
                    started_at TEXT,
                    completed_at TEXT
                );
                """
            )
            conn.execute(
                "INSERT INTO workspaces (id, mode) VALUES (?, ?)",
                ("legacy-workspace", "personal"),
            )
            conn.commit()
        finally:
            conn.close()

    def _columns_for(self, table_name: str) -> set[str]:
        conn = sqlite3.connect(self.db_path)
        try:
            return {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
        finally:
            conn.close()

    def test_local_startup_migrates_legacy_workspace_tables(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

        workspace_columns = self._columns_for("workspaces")
        self.assertIn("owner_user_id", workspace_columns)
        self.assertIn("name", workspace_columns)
        self.assertIn("slug", workspace_columns)
        self.assertIn("plan", workspace_columns)
        self.assertIn("subscription_status", workspace_columns)

        resume_columns = self._columns_for("workspace_resumes")
        self.assertIn("file_asset_id", resume_columns)
        self.assertIn("storage_provider", resume_columns)
        self.assertIn("storage_path", resume_columns)
        self.assertIn("file_sha256", resume_columns)

        run_columns = self._columns_for("workspace_search_runs")
        self.assertIn("request_json", run_columns)
        self.assertIn("attempt_count", run_columns)
        self.assertIn("max_attempts", run_columns)
        self.assertIn("available_at", run_columns)
        self.assertIn("created_at", run_columns)
        self.assertIn("updated_at", run_columns)


if __name__ == "__main__":
    unittest.main()
