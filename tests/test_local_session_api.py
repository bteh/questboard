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


class LocalSessionBootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {
            key: os.environ.get(key)
            for key in [
                "DATA_DIR",
                "WORKSPACE_STORAGE_DIR",
                "HOSTED_MODE",
                "MANAGE_SCHEMA_ON_STARTUP",
                "DATABASE_URL",
                "LAUNCHBOARD_DESKTOP_MODE",
                "LLM_PROVIDER",
                "LLM_BASE_URL",
                "LLM_API_KEY",
                "LLM_MODEL",
            ]
        }
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-local-session-test-")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.workspace_dir = os.path.join(self.temp_dir, "workspaces")
        self.db_path = os.path.join(self.data_dir, "job_tracker.db")
        os.makedirs(self.data_dir, exist_ok=True)

        os.environ["DATA_DIR"] = self.data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = self.workspace_dir
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"

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

        app_main = importlib.import_module("app.main")
        self.scheduler_start = patch.object(app_main, "start_scheduler", lambda: None)
        self.scheduler_stop = patch.object(app_main, "stop_scheduler", lambda: None)
        self.scheduler_start.start()
        self.scheduler_stop.start()
        self.addCleanup(self.scheduler_start.stop)
        self.addCleanup(self.scheduler_stop.stop)

        self.client_one = TestClient(app_main.app)
        self.client_two = TestClient(app_main.app)
        self.addCleanup(self.client_one.close)
        self.addCleanup(self.client_two.close)

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bootstrap_creates_unique_named_local_workspaces(self) -> None:
        first = self.client_one.post("/api/v1/session/bootstrap")
        second = self.client_two.post("/api/v1/session/bootstrap")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()["workspace_id"], second.json()["workspace_id"])

        db_gen = self.backend_db.get_db()
        db = next(db_gen)
        try:
            workspace_model = importlib.import_module("app.models.workspace").Workspace
            workspaces = db.query(workspace_model).order_by(workspace_model.created_at.asc()).all()
        finally:
            db_gen.close()

        self.assertEqual(len(workspaces), 2)
        self.assertEqual([workspace.name for workspace in workspaces], ["Local workspace", "Local workspace"])
        self.assertTrue(all(workspace.slug for workspace in workspaces))
        self.assertEqual(len({workspace.slug for workspace in workspaces}), 2)

    def test_bootstrap_normalizes_legacy_anonymous_workspace_identity(self) -> None:
        initial = self.client_one.post("/api/v1/session/bootstrap")
        self.assertEqual(initial.status_code, 200)
        workspace_id = initial.json()["workspace_id"]

        db_gen = self.backend_db.get_db()
        db = next(db_gen)
        try:
            workspace_model = importlib.import_module("app.models.workspace").Workspace
            workspace = db.query(workspace_model).filter(workspace_model.id == workspace_id).first()
            workspace.name = "Workspace"
            workspace.slug = workspace.id
            db.commit()
        finally:
            db_gen.close()

        refreshed = self.client_one.post("/api/v1/session/bootstrap")
        self.assertEqual(refreshed.status_code, 200)

        db_gen = self.backend_db.get_db()
        db = next(db_gen)
        try:
            workspace_model = importlib.import_module("app.models.workspace").Workspace
            workspace = db.query(workspace_model).filter(workspace_model.id == workspace_id).first()
        finally:
            db_gen.close()

        self.assertEqual(workspace.name, "Local workspace")
        self.assertTrue(workspace.slug)
        self.assertNotEqual(workspace.slug, workspace.id)

    def test_desktop_mode_supports_header_based_workspace_session_and_resume_upload(self) -> None:
        os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"

        desktop_client = TestClient(importlib.import_module("app.main").app)
        self.addCleanup(desktop_client.close)

        bootstrap = desktop_client.post("/api/v1/session/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        payload = bootstrap.json()
        self.assertTrue(payload["session_token"])
        self.assertTrue(payload["csrf_token"])

        headers = {
            "X-Launchboard-Session": payload["session_token"],
            "X-CSRF-Token": payload["csrf_token"],
        }

        state = desktop_client.get("/api/v1/onboarding/state", headers={
            "X-Launchboard-Session": payload["session_token"],
        })
        self.assertEqual(state.status_code, 200)

        upload = desktop_client.post(
            "/api/v1/onboarding/resume",
            headers=headers,
            files={"file": ("resume.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF", "application/pdf")},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertTrue(upload.json()["resume"]["exists"])

    def test_desktop_mode_can_resume_workspace_from_header_only_bootstrap(self) -> None:
        os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"

        first_client = TestClient(importlib.import_module("app.main").app)
        second_client = TestClient(importlib.import_module("app.main").app)
        self.addCleanup(first_client.close)
        self.addCleanup(second_client.close)

        bootstrap = first_client.post("/api/v1/session/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        payload = bootstrap.json()

        resumed = second_client.post(
            "/api/v1/session/bootstrap",
            headers={"X-Launchboard-Session": payload["session_token"]},
        )
        self.assertEqual(resumed.status_code, 200)
        resumed_payload = resumed.json()

        self.assertEqual(resumed_payload["workspace_id"], payload["workspace_id"])
        self.assertEqual(resumed_payload["session_token"], payload["session_token"])
        self.assertTrue(resumed_payload["csrf_token"])

    def test_desktop_mode_header_session_powers_workspace_defaults(self) -> None:
        os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"

        desktop_client = TestClient(importlib.import_module("app.main").app)
        self.addCleanup(desktop_client.close)

        bootstrap = desktop_client.post("/api/v1/session/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        payload = bootstrap.json()
        headers = {
            "X-Launchboard-Session": payload["session_token"],
            "X-CSRF-Token": payload["csrf_token"],
        }

        preferences = {
            "roles": ["Data Platform Engineering Manager"],
            "keywords": ["lakehouse", "dbt"],
            "companies": ["Databricks"],
            "preferred_places": [
                {
                    "label": "Los Angeles, CA",
                    "kind": "city",
                    "match_scope": "city",
                    "city": "Los Angeles",
                    "region": "CA",
                    "country": "United States",
                    "country_code": "us",
                    "lat": None,
                    "lon": None,
                    "provider": "manual",
                    "provider_id": "",
                }
            ],
            "workplace_preference": "remote_friendly",
            "max_days_old": 14,
            "include_linkedin_jobs": False,
            "current_title": "Engineering Manager",
            "current_level": "manager",
            "compensation": {
                "currency": "USD",
                "pay_period": "annual",
                "current_comp": None,
                "min_base": 150000,
                "target_total_comp": 220000,
                "min_acceptable_tc": None,
                "include_equity": True,
            },
            "exclude_staffing_agencies": True,
        }

        save = desktop_client.post("/api/v1/onboarding/preferences", headers=headers, json=preferences)
        self.assertEqual(save.status_code, 200)

        defaults = desktop_client.get(
            "/api/v1/search/defaults?profile=default",
            headers={"X-Launchboard-Session": payload["session_token"]},
        )
        self.assertEqual(defaults.status_code, 200)
        data = defaults.json()
        self.assertEqual(data["profile"], "workspace")
        self.assertEqual(data["roles"], ["Data Platform Engineering Manager"])
        self.assertEqual(data["keywords"], ["lakehouse", "dbt"])
        self.assertEqual(data["companies"], ["Databricks"])
        self.assertEqual(data["locations"], ["Los Angeles, CA"])

    def test_desktop_mode_does_not_inherit_global_llm_env(self) -> None:
        os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_BASE_URL"] = "http://localhost:8317/v1"
        os.environ["LLM_API_KEY"] = "desktop-env-key"
        os.environ["LLM_MODEL"] = "claude-opus-4-5-20251101"

        desktop_client = TestClient(importlib.import_module("app.main").app)
        self.addCleanup(desktop_client.close)

        bootstrap = desktop_client.post("/api/v1/session/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        payload = bootstrap.json()

        status = desktop_client.get(
            "/api/v1/settings/llm",
            headers={"X-Launchboard-Session": payload["session_token"]},
        )
        self.assertEqual(status.status_code, 200, status.text)
        data = status.json()
        self.assertFalse(data["configured"])
        self.assertTrue(data["runtime_configurable"])

    def test_desktop_mode_starts_with_blank_onboarding_preferences(self) -> None:
        os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"

        desktop_client = TestClient(importlib.import_module("app.main").app)
        self.addCleanup(desktop_client.close)

        bootstrap = desktop_client.post("/api/v1/session/bootstrap")
        self.assertEqual(bootstrap.status_code, 200)
        payload = bootstrap.json()

        state = desktop_client.get(
            "/api/v1/onboarding/state",
            headers={"X-Launchboard-Session": payload["session_token"]},
        )
        self.assertEqual(state.status_code, 200, state.text)
        data = state.json()
        self.assertFalse(data["has_started_search"])
        self.assertFalse(data["ready_to_search"])
        self.assertEqual(data["preferences"]["roles"], [])
        self.assertEqual(data["preferences"]["keywords"], [])
        self.assertEqual(data["preferences"]["companies"], [])
        self.assertEqual(data["preferences"]["preferred_places"], [])
