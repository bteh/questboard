"""GET /search/defaults must default match_strictness to 'balanced'.

Covers both branches of get_search_defaults:
  - the non-workspace config fallback (was hardcoded 'loose'),
  - the workspace branch for a freshly bootstrapped session (model default).
"""

from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for p in (BACKEND_PATH, SRC_PATH):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class SearchDefaultsStrictnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = {
            k: os.environ.get(k)
            for k in [
                "DATA_DIR", "WORKSPACE_STORAGE_DIR", "HOSTED_MODE",
                "MANAGE_SCHEMA_ON_STARTUP", "DATABASE_URL", "QUESTBOARD_DESKTOP_MODE",
            ]
        }
        self.temp_dir = tempfile.mkdtemp(prefix="questboard-defaults-test-")
        data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "job_tracker.db")
        os.environ["DATA_DIR"] = data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = os.path.join(self.temp_dir, "workspaces")
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["QUESTBOARD_DESKTOP_MODE"] = "true"
        for name in list(sys.modules):
            if name == "app" or name.startswith("app.") or name.startswith("job_finder.models"):
                sys.modules.pop(name, None)
        importlib.import_module("app.models.database").init_db(self.db_path)

    def tearDown(self) -> None:
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_fallback_defaults_to_balanced(self) -> None:
        """No workspace context + default profile (no filters block) → balanced."""
        search = importlib.import_module("app.api.search")
        result = asyncio.run(
            search.get_search_defaults(profile="default", workspace=None, db=None)
        )
        self.assertEqual(result.match_strictness, "balanced")

    def test_new_workspace_defaults_to_balanced(self) -> None:
        """A freshly bootstrapped workspace exposes balanced, not loose."""
        from fastapi.testclient import TestClient

        app_main = importlib.import_module("app.main")
        with TestClient(app_main.app) as client:
            bootstrap = client.post("/api/v1/session/bootstrap")
            self.assertEqual(bootstrap.status_code, 200, bootstrap.text)
            token = bootstrap.json()["csrf_token"]
            resp = client.get("/api/v1/search/defaults", headers={"X-CSRF-Token": token})
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(resp.json()["match_strictness"], "balanced")


if __name__ == "__main__":
    unittest.main()
