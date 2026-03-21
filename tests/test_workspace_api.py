from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import importlib
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


class WorkspaceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-workspace-test-")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.workspace_dir = os.path.join(self.temp_dir, "workspaces")
        self.db_path = os.path.join(self.data_dir, "job_tracker.db")
        os.makedirs(self.data_dir, exist_ok=True)
        os.environ["DATA_DIR"] = self.data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = self.workspace_dir
        os.environ["HOSTED_MODE"] = "true"
        os.environ["SESSION_SECURE_COOKIES"] = "false"
        os.environ["ALLOW_RUNTIME_LLM_CONFIG"] = "false"

        sys.modules.pop("app", None)
        backend_db = importlib.import_module("app.models.database")
        security = importlib.import_module("app.security")
        pipeline_service = importlib.import_module("app.services.pipeline_service")

        backend_db.init_db(self.db_path)
        security._WINDOWS.clear()
        pipeline_service._runs.clear()

        app_main = importlib.import_module("app.main")

        self.scheduler_start = patch.object(app_main, "start_scheduler", lambda: None)
        self.scheduler_stop = patch.object(app_main, "stop_scheduler", lambda: None)
        self.scheduler_start.start()
        self.scheduler_stop.start()
        self.addCleanup(self.scheduler_start.stop)
        self.addCleanup(self.scheduler_stop.stop)
        self.client = TestClient(app_main.app)
        self.addCleanup(self.client.close)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _bootstrap(self, client: TestClient | None = None) -> dict:
        active_client = client or self.client
        response = active_client.post("/api/v1/session/bootstrap")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("workspace_id", payload)
        self.assertIn("lb_session", active_client.cookies)
        self.assertIn("lb_csrf", active_client.cookies)
        return payload

    def _csrf_headers(self, client: TestClient | None = None) -> dict[str, str]:
        active_client = client or self.client
        return {"X-CSRF-Token": active_client.cookies.get("lb_csrf", "")}

    def test_bootstrap_sets_isolated_session_and_onboarding_state(self) -> None:
        session = self._bootstrap()
        state = self.client.get("/api/v1/onboarding/state")
        self.assertEqual(state.status_code, 200)
        payload = state.json()
        self.assertEqual(payload["workspace_id"], session["workspace_id"])
        self.assertTrue(payload["needs_resume"])
        self.assertTrue(payload["needs_preferences"])
        self.assertEqual(payload["resume"]["parse_status"], "missing")
        self.assertIn("preferences", payload)

    def test_preferences_endpoint_rejects_missing_or_invalid_csrf(self) -> None:
        self._bootstrap()
        prefs = self.client.get("/api/v1/onboarding/state").json()["preferences"]

        missing = self.client.post("/api/v1/onboarding/preferences", json=prefs)
        self.assertEqual(missing.status_code, 403)

        invalid = self.client.post(
            "/api/v1/onboarding/preferences",
            json=prefs,
            headers={"X-CSRF-Token": "wrong-token"},
        )
        self.assertEqual(invalid.status_code, 403)

        ok = self.client.post(
            "/api/v1/onboarding/preferences",
            json={**prefs, "current_title": "Registered Nurse"},
            headers=self._csrf_headers(),
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["current_title"], "Registered Nurse")

    def test_resume_upload_rejects_invalid_pdf_magic_bytes(self) -> None:
        self._bootstrap()
        response = self.client.post(
            "/api/v1/onboarding/resume",
            files={"file": ("resume.pdf", b"not-a-pdf", "application/pdf")},
            headers=self._csrf_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid PDF", response.json()["detail"])

    def test_resume_upload_updates_workspace_preferences(self) -> None:
        self._bootstrap()
        pdf_bytes = b"%PDF-1.4\nmock pdf payload"

        with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value="Experienced nurse practitioner"), patch(
            "app.services.resume_analyzer.analyze_resume",
            return_value={
                "suggested_target_roles": ["Nurse Practitioner"],
                "suggested_keywords": ["Primary Care", "Telehealth"],
                "current_title": "Nurse Practitioner",
                "seniority": "senior",
            },
        ):
            response = self.client.post(
                "/api/v1/onboarding/resume",
                files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
                headers=self._csrf_headers(),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resume"]["parse_status"], "parsed")
        self.assertEqual(payload["analysis"]["current_title"], "Nurse Practitioner")

        state = self.client.get("/api/v1/onboarding/state").json()
        self.assertEqual(state["preferences"]["roles"], ["Nurse Practitioner"])
        self.assertEqual(state["preferences"]["keywords"], ["Primary Care", "Telehealth"])
        self.assertEqual(state["preferences"]["current_title"], "Nurse Practitioner")
        self.assertEqual(state["preferences"]["current_level"], "senior")

        workspace_root = Path(self.workspace_dir) / state["workspace_id"]
        self.assertTrue(workspace_root.exists())
        self.assertTrue(any(path.suffix == ".pdf" for path in workspace_root.iterdir()))

    def test_search_defaults_reflect_workspace_preferences(self) -> None:
        self._bootstrap()
        prefs = self.client.get("/api/v1/onboarding/state").json()["preferences"]
        updated = {
            **prefs,
            "roles": ["Teacher"],
            "keywords": ["Curriculum Design", "K-12"],
            "preferred_places": [
                {
                    "label": "Berlin, Germany",
                    "kind": "city",
                    "city": "Berlin",
                    "region": "Berlin",
                    "country": "Germany",
                    "country_code": "DE",
                    "lat": 52.52,
                    "lon": 13.405,
                    "provider": "local",
                    "provider_id": "Berlin, Germany",
                }
            ],
            "workplace_preference": "location_only",
            "max_days_old": 7,
            "current_title": "Teacher",
            "current_level": "mid",
            "compensation": {
                "currency": "EUR",
                "pay_period": "annual",
                "current_comp": 55000,
                "min_base": 50000,
                "target_total_comp": 65000,
                "min_acceptable_tc": 48000,
                "include_equity": False,
            },
            "exclude_staffing_agencies": True,
        }
        save = self.client.post(
            "/api/v1/onboarding/preferences",
            json=updated,
            headers=self._csrf_headers(),
        )
        self.assertEqual(save.status_code, 200)

        defaults = self.client.get("/api/v1/search/defaults?profile=default")
        self.assertEqual(defaults.status_code, 200)
        payload = defaults.json()
        self.assertEqual(payload["profile"], "workspace")
        self.assertEqual(payload["roles"], ["Teacher"])
        self.assertEqual(payload["locations"], ["Berlin, Germany"])
        self.assertEqual(payload["current_title"], "Teacher")
        self.assertEqual(payload["current_level"], "mid")
        self.assertEqual(payload["compensation_currency"], "EUR")
        self.assertEqual(payload["target_total_comp"], 65000)

    def test_search_run_endpoints_are_workspace_scoped(self) -> None:
        session_a = self._bootstrap()
        from app.services import pipeline_service
        from app.services.pipeline_service import PipelineRun

        client_b = TestClient(self.client.app)
        self.addCleanup(client_b.close)
        session_b = self._bootstrap(client_b)

        run_a = PipelineRun(run_id="run-a", profile="workspace", mode="search_score", workspace_id=session_a["workspace_id"], status="running")
        run_b = PipelineRun(run_id="run-b", profile="workspace", mode="search_score", workspace_id=session_b["workspace_id"], status="running")
        pipeline_service._runs["run-a"] = run_a
        pipeline_service._runs["run-b"] = run_b

        runs_a = self.client.get("/api/v1/search/runs")
        self.assertEqual(runs_a.status_code, 200)
        self.assertEqual([item["run_id"] for item in runs_a.json()], ["run-a"])

        blocked = self.client.get("/api/v1/search/runs/run-b/status")
        self.assertEqual(blocked.status_code, 404)

        client_c = TestClient(self.client.app)
        self.addCleanup(client_c.close)
        no_session_runs = client_c.get("/api/v1/search/runs")
        self.assertEqual(no_session_runs.status_code, 200)
        self.assertEqual(no_session_runs.json(), [])

    def test_location_suggest_uses_session_and_local_fallback(self) -> None:
        self._bootstrap()
        response = self.client.get("/api/v1/locations/suggest?q=berl")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item["label"] == "Berlin, Germany" for item in payload))
        self.assertTrue(any(item["provider"] == "local" for item in payload))

    def test_runtime_llm_config_is_disabled_by_default(self) -> None:
        response = self.client.put(
            "/api/v1/settings/llm",
            json={
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": "test-key",
                "model": "gpt-4o-mini",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_workspace_llm_config_is_user_configurable(self) -> None:
        self._bootstrap()

        status = self.client.get("/api/v1/settings/llm")
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json()["runtime_configurable"])

        with patch("job_finder.llm_client.LLMClient.is_available", return_value=True):
            updated = self.client.put(
                "/api/v1/settings/llm",
                json={
                    "provider": "openai-api",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "workspace-key",
                    "model": "gpt-4o-mini",
                },
                headers=self._csrf_headers(),
            )

        self.assertEqual(updated.status_code, 200)
        payload = updated.json()
        self.assertEqual(payload["provider"], "openai-api")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertTrue(payload["runtime_configurable"])


if __name__ == "__main__":
    unittest.main()
