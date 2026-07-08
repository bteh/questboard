"""Regression test for POST /applications/check-urls.

The route previously declared `ids: list[int] | None = None` plus a `Query`-defaulted
`limit` parameter. FastAPI inferred the entire request body as the `ids` list,
so the frontend's `{"ids": [...], "limit": N}` payload failed with 422
("Input should be a valid list"). The fix wraps both fields in a Pydantic body
model. This test pins the contract so it doesn't silently regress.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

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


class CheckUrlsBodyContractTest(unittest.TestCase):
    """The endpoint must accept the frontend's JSON body shape."""

    def setUp(self) -> None:
        self._original_env = {
            key: os.environ.get(key)
            for key in [
                "DATA_DIR",
                "WORKSPACE_STORAGE_DIR",
                "HOSTED_MODE",
                "MANAGE_SCHEMA_ON_STARTUP",
                "DATABASE_URL",
                "QUESTBOARD_DESKTOP_MODE",
            ]
        }
        self.temp_dir = tempfile.mkdtemp(prefix="questboard-check-urls-test-")
        data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "job_tracker.db")

        os.environ["DATA_DIR"] = data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = os.path.join(self.temp_dir, "workspaces")
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        # Desktop mode makes /session/bootstrap return the CSRF token in the
        # response body (cookies aren't carried by TestClient across requests
        # the same way as a browser).
        os.environ["QUESTBOARD_DESKTOP_MODE"] = "true"

        for module_name in list(sys.modules):
            if (
                module_name == "app"
                or module_name.startswith("app.")
                or module_name == "job_finder.models"
                or module_name.startswith("job_finder.models.")
            ):
                sys.modules.pop(module_name, None)

        backend_db = importlib.import_module("app.models.database")
        backend_db.init_db(db_path)

        app_main = importlib.import_module("app.main")
        self.client = TestClient(app_main.app)
        self.addCleanup(self.client.close)

        bootstrap = self.client.post("/api/v1/session/bootstrap")
        self.assertEqual(bootstrap.status_code, 200, bootstrap.text)
        self.csrf_headers = {"X-CSRF-Token": bootstrap.json()["csrf_token"]}

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _post(self, body: dict) -> tuple[int, dict | str]:
        response = self.client.post(
            "/api/v1/applications/check-urls",
            json=body,
            headers=self.csrf_headers,
        )
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, response.text

    def test_accepts_frontend_body_with_limit_only(self) -> None:
        status, payload = self._post({"limit": 5})
        self.assertEqual(status, 200, payload)
        self.assertIn("checked", payload)
        self.assertIn("alive", payload)
        self.assertIn("dead", payload)

    def test_accepts_body_with_ids_and_limit(self) -> None:
        status, payload = self._post({"ids": [], "limit": 10})
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["checked"], 0)

    def test_accepts_empty_body(self) -> None:
        status, payload = self._post({})
        self.assertEqual(status, 200, payload)

    def test_rejects_invalid_limit(self) -> None:
        status, _ = self._post({"limit": 0})
        self.assertEqual(status, 422)


if __name__ == "__main__":
    unittest.main()
