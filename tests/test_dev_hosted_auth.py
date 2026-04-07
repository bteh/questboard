from __future__ import annotations

import importlib
import os
import shutil
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


class DevHostedAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {key: os.environ.get(key) for key in [
            "DATA_DIR",
            "WORKSPACE_STORAGE_DIR",
            "HOSTED_MODE",
            "DEV_HOSTED_AUTH",
            "DEV_HOSTED_AUTH_SECRET",
            "MANAGE_SCHEMA_ON_STARTUP",
            "DATABASE_URL",
            "SUPABASE_URL",
            "SUPABASE_JWT_AUDIENCE",
            "EMBEDDED_SCHEDULER_ENABLED",
        ]}
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-dev-hosted-auth-")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.workspace_dir = os.path.join(self.temp_dir, "workspaces")
        self.db_path = os.path.join(self.data_dir, "job_tracker.db")
        os.makedirs(self.data_dir, exist_ok=True)
        os.environ["DATA_DIR"] = self.data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = self.workspace_dir
        os.environ["HOSTED_MODE"] = "true"
        os.environ["DEV_HOSTED_AUTH"] = "true"
        os.environ["DEV_HOSTED_AUTH_SECRET"] = "launchboard-dev-secret-key-1234567890"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ.pop("SUPABASE_URL", None)
        os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"
        os.environ["EMBEDDED_SCHEDULER_ENABLED"] = "false"

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
        self.workspace_service = importlib.import_module("app.services.workspace_service")
        self.dev_auth_service = importlib.import_module("app.services.dev_auth_service")
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

    def _get_db(self):
        db_gen = self.backend_db.get_db()
        db = next(db_gen)
        self.addCleanup(lambda: db_gen.close())
        return db

    def _login(self, persona_id: str) -> tuple[dict[str, str], dict]:
        response = self.client.post("/api/v1/dev/auth/login", json={"persona_id": persona_id})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        return {"Authorization": f"Bearer {payload['access_token']}"}, payload

    def _register(self, email: str, full_name: str) -> tuple[dict[str, str], dict]:
        response = self.client.post(
            "/api/v1/dev/auth/register",
            json={"email": email, "full_name": full_name},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        return {"Authorization": f"Bearer {payload['access_token']}"}, payload

    def test_register_creates_blank_hosted_workspace(self) -> None:
        headers, payload = self._register("test.user@example.com", "Test User")
        self.assertEqual(payload["user"]["email"], "test.user@example.com")
        self.assertFalse(payload["user"]["seeded"])

        me = self.client.get("/api/v1/me", headers=headers)
        self.assertEqual(me.status_code, 200, me.text)
        bootstrap = me.json()
        self.assertEqual(bootstrap["user"]["email"], "test.user@example.com")
        self.assertEqual(bootstrap["workspace"]["name"], "Test User sandbox")

        state = self.client.get("/api/v1/onboarding/state", headers=headers)
        self.assertEqual(state.status_code, 200, state.text)
        onboarding = state.json()
        self.assertFalse(onboarding["has_started_search"])
        self.assertTrue(onboarding["needs_resume"])
        self.assertTrue(onboarding["needs_preferences"])
        self.assertFalse(onboarding["ready_to_search"])
        self.assertFalse(onboarding["resume"]["exists"])
        self.assertEqual(onboarding["preferences"]["roles"], [])
        self.assertEqual(onboarding["preferences"]["keywords"], [])
        self.assertEqual(onboarding["preferences"]["current_title"], "")

    def test_persona_listing_and_login_seed_workspace(self) -> None:
        personas_response = self.client.get("/api/v1/dev/auth/personas")
        self.assertEqual(personas_response.status_code, 200)
        personas = personas_response.json()
        self.assertGreaterEqual(len(personas), 4)
        self.assertEqual(personas[0]["resume_filename"].endswith(".pdf"), True)

        headers, payload = self._login("maya-chen")
        self.assertEqual(payload["persona"]["full_name"], "Maya Chen")

        me = self.client.get("/api/v1/me", headers=headers)
        self.assertEqual(me.status_code, 200, me.text)
        bootstrap = me.json()
        self.assertEqual(bootstrap["user"]["id"], "maya-chen")
        self.assertEqual(bootstrap["workspace"]["name"], "Maya Chen sandbox")

        state = self.client.get("/api/v1/onboarding/state", headers=headers)
        self.assertEqual(state.status_code, 200, state.text)
        onboarding = state.json()
        self.assertFalse(onboarding["has_started_search"])
        self.assertFalse(onboarding["needs_resume"])
        self.assertFalse(onboarding["needs_preferences"])
        self.assertTrue(onboarding["resume"]["exists"])
        self.assertEqual(onboarding["preferences"]["current_title"], "Principal Product Designer")
        self.assertIn("Staff Product Designer", onboarding["preferences"]["roles"])

        db = self._get_db()
        resume = self.workspace_service.get_workspace_resume(db, bootstrap["workspace"]["id"])
        self.assertIsNotNone(resume)
        self.assertEqual(resume.parse_status, "parsed")
        self.assertTrue(resume.file_asset_id)
        self.assertIn("AI-assisted experiences", resume.extracted_text)

    def test_personas_have_isolated_workspace_state(self) -> None:
        maya_headers, _ = self._login("maya-chen")
        diego_headers, _ = self._login("diego-alvarez")

        maya_state = self.client.get("/api/v1/onboarding/state", headers=maya_headers).json()
        diego_state = self.client.get("/api/v1/onboarding/state", headers=diego_headers).json()

        self.assertNotEqual(maya_state["workspace_id"], diego_state["workspace_id"])
        self.assertEqual(maya_state["preferences"]["current_title"], "Principal Product Designer")
        self.assertEqual(diego_state["preferences"]["current_title"], "Staff Data Engineer")

        updated = {
            **maya_state["preferences"],
            "roles": ["Design Director"],
            "keywords": ["AI strategy", "design systems"],
        }
        save = self.client.post("/api/v1/onboarding/preferences", headers=maya_headers, json=updated)
        self.assertEqual(save.status_code, 200, save.text)

        refreshed_maya = self.client.get("/api/v1/onboarding/state", headers=maya_headers).json()
        refreshed_diego = self.client.get("/api/v1/onboarding/state", headers=diego_headers).json()
        self.assertEqual(refreshed_maya["preferences"]["roles"], ["Design Director"])
        self.assertEqual(refreshed_diego["preferences"]["current_title"], "Staff Data Engineer")
        self.assertIn("AI Platform Engineer", refreshed_diego["preferences"]["roles"])


if __name__ == "__main__":
    unittest.main()
