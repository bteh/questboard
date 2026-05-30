"""Local (non-hosted) run history must survive an in-memory wipe.

Bug: in local mode, run status/history were served only from pipeline_service's
in-process `_runs` dict, which is wiped on every uvicorn --reload (every code
save) and on restart. The runs ARE persisted to workspace_search_runs, but the
non-hosted API branches never read them back — so the UI lost its "latest run"
anchor and /applications?run=... 404'd, making results feel stale/lost.

Contract: when the in-memory run is gone but a persisted run exists for the
active local workspace, /search/runs and /search/runs/{id}/status return it.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for p in (BACKEND_PATH, SRC_PATH):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class LocalRunPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = {
            k: os.environ.get(k)
            for k in ["DATA_DIR", "WORKSPACE_STORAGE_DIR", "HOSTED_MODE",
                      "MANAGE_SCHEMA_ON_STARTUP", "DATABASE_URL", "LAUNCHBOARD_DESKTOP_MODE"]
        }
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-runpersist-")
        data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "job_tracker.db")
        os.environ["DATA_DIR"] = data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = os.path.join(self.temp_dir, "workspaces")
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"
        for name in list(sys.modules):
            if name == "app" or name.startswith("app.") or name.startswith("job_finder.models"):
                sys.modules.pop(name, None)
        self.backend_db = importlib.import_module("app.models.database")
        self.backend_db.init_db(self.db_path)
        self.app_main = importlib.import_module("app.main")
        self.pipeline_service = importlib.import_module("app.services.pipeline_service")
        self.WorkspaceSearchRun = importlib.import_module("app.models.workspace").WorkspaceSearchRun
        self.Workspace = importlib.import_module("app.models.workspace").Workspace
        self.client = TestClient(self.app_main.app)
        self.addCleanup(self.client.close)
        boot = self.client.post("/api/v1/session/bootstrap")
        self.assertEqual(boot.status_code, 200, boot.text)
        self.csrf = {"X-CSRF-Token": boot.json()["csrf_token"]}

    def tearDown(self) -> None:
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _workspace_id(self) -> str:
        db = self.backend_db._SessionLocal()
        try:
            ws = db.query(self.Workspace).first()
            self.assertIsNotNone(ws, "bootstrap should have created a local workspace")
            return ws.id
        finally:
            db.close()

    def _insert_completed_run(self, ws_id: str, run_id: str, jobs: int) -> None:
        db = self.backend_db._SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            db.add(self.WorkspaceSearchRun(
                workspace_id=ws_id, run_id=run_id, status="completed",
                jobs_found=jobs, jobs_scored=jobs, strong_matches=1,
                started_at=now, completed_at=now,
            ))
            db.commit()
        finally:
            db.close()

    def test_runs_survive_in_memory_wipe(self) -> None:
        ws_id = self._workspace_id()
        self._insert_completed_run(ws_id, "persistedrun01", jobs=42)
        # Simulate a uvicorn --reload / restart wiping in-memory runs.
        self.pipeline_service._runs.clear()

        runs = self.client.get("/api/v1/search/runs", headers=self.csrf)
        self.assertEqual(runs.status_code, 200, runs.text)
        ids = [r["run_id"] for r in runs.json()]
        self.assertIn("persistedrun01", ids)

        status = self.client.get("/api/v1/search/runs/persistedrun01/status", headers=self.csrf)
        self.assertEqual(status.status_code, 200, status.text)
        body = status.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["jobs_found"], 42)


if __name__ == "__main__":
    unittest.main()
