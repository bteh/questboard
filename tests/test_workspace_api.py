from __future__ import annotations

import asyncio
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jwt
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


TEST_JWT_SECRET = "test-supabase-secret-with-32-bytes"


class HostedWorkspaceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env = {key: os.environ.get(key) for key in [
            "DATA_DIR",
            "WORKSPACE_STORAGE_DIR",
            "HOSTED_MODE",
            "DEV_HOSTED_AUTH",
            "SESSION_SECURE_COOKIES",
            "ALLOW_RUNTIME_LLM_CONFIG",
            "HOSTED_ALLOW_WORKSPACE_LLM_CONFIG",
            "HOSTED_PLATFORM_MANAGED_AI",
            "SUPABASE_URL",
            "SUPABASE_JWT_SECRET",
            "SUPABASE_JWT_AUDIENCE",
            "MANAGE_SCHEMA_ON_STARTUP",
            "DATABASE_URL",
            "APP_RELEASE",
            "LAUNCHBOARD_SECRET",
            "LLM_PROVIDER",
            "LLM_BASE_URL",
            "LLM_MODEL",
            "LLM_API_KEY",
        ]}
        self.temp_dir = tempfile.mkdtemp(prefix="launchboard-hosted-test-")
        self.data_dir = os.path.join(self.temp_dir, "data")
        self.workspace_dir = os.path.join(self.temp_dir, "workspaces")
        self.db_path = os.path.join(self.data_dir, "job_tracker.db")
        os.makedirs(self.data_dir, exist_ok=True)
        os.environ["DATA_DIR"] = self.data_dir
        os.environ["WORKSPACE_STORAGE_DIR"] = self.workspace_dir
        os.environ["HOSTED_MODE"] = "true"
        os.environ["SESSION_SECURE_COOKIES"] = "false"
        os.environ["ALLOW_RUNTIME_LLM_CONFIG"] = "false"
        os.environ["HOSTED_ALLOW_WORKSPACE_LLM_CONFIG"] = "false"
        os.environ["HOSTED_PLATFORM_MANAGED_AI"] = "true"
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
        os.environ["SUPABASE_JWT_AUDIENCE"] = "authenticated"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["APP_RELEASE"] = "test-release"

        for module_name in list(sys.modules):
            if (
                module_name == "app"
                or module_name.startswith("app.")
                or module_name == "job_finder.models"
                or module_name.startswith("job_finder.models.")
            ):
                sys.modules.pop(module_name, None)
        backend_db = importlib.import_module("app.models.database")
        pipeline_service = importlib.import_module("app.services.pipeline_service")
        workspace_service = importlib.import_module("app.services.workspace_service")

        backend_db.init_db(self.db_path)
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
        self.backend_db = backend_db
        self.pipeline_service = pipeline_service
        self.workspace_service = workspace_service

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _token(
        self,
        *,
        user_id: str,
        email: str,
        full_name: str = "Launchboard User",
    ) -> str:
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
            "user_metadata": {"full_name": full_name},
        }
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    def _auth_headers(
        self,
        *,
        user_id: str = "user-a",
        email: str = "user-a@example.com",
        full_name: str = "User A",
    ) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token(user_id=user_id, email=email, full_name=full_name)}",
        }

    def _get_db(self):
        db_gen = self.backend_db.get_db()
        db = next(db_gen)
        self.addCleanup(lambda: db_gen.close())
        return db

    def test_me_bootstraps_profile_workspace_and_onboarding_state(self) -> None:
        headers = self._auth_headers()

        me = self.client.get("/api/v1/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        payload = me.json()
        self.assertTrue(payload["hosted_mode"])
        self.assertTrue(payload["auth_required"])
        self.assertFalse(payload["csrf_required"])
        self.assertEqual(payload["user"]["email"], "user-a@example.com")
        self.assertEqual(payload["workspace"]["plan"], "free")
        self.assertFalse(payload["features"]["runtime_llm_configurable"])

        state = self.client.get("/api/v1/onboarding/state", headers=headers)
        self.assertEqual(state.status_code, 200)
        onboarding = state.json()
        self.assertEqual(onboarding["workspace_id"], payload["workspace"]["id"])
        self.assertFalse(onboarding["has_started_search"])
        self.assertTrue(onboarding["needs_resume"])
        self.assertTrue(onboarding["needs_preferences"])

    def test_resume_upload_persists_workspace_asset_and_preferences(self) -> None:
        headers = self._auth_headers()
        me = self.client.get("/api/v1/me", headers=headers).json()
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
                headers=headers,
                files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["resume"]["parse_status"], "parsed")
        self.assertEqual(payload["analysis"]["current_title"], "Nurse Practitioner")

        state = self.client.get("/api/v1/onboarding/state", headers=headers).json()
        self.assertEqual(state["preferences"]["roles"], ["Nurse Practitioner"])
        self.assertEqual(state["preferences"]["keywords"], ["Primary Care", "Telehealth"])
        self.assertEqual(state["preferences"]["current_level"], "senior")

        db = self._get_db()
        resume_record = self.workspace_service.get_workspace_resume(db, me["workspace"]["id"])
        self.assertIsNotNone(resume_record)
        self.assertTrue(resume_record.file_asset_id)
        asset = self.workspace_service.get_file_asset(db, resume_record.file_asset_id)
        self.assertIsNotNone(asset)
        self.assertEqual(asset.kind, "resume")

    def test_search_defaults_reflect_workspace_preferences(self) -> None:
        headers = self._auth_headers()
        me = self.client.get("/api/v1/me", headers=headers).json()
        prefs = self.client.get("/api/v1/onboarding/state", headers=headers).json()["preferences"]
        updated = {
            **prefs,
            "roles": ["Teacher"],
            "keywords": ["Curriculum Design", "K-12"],
            "companies": ["Khan Academy", "Coursera"],
            "include_linkedin_jobs": True,
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
        save = self.client.post("/api/v1/onboarding/preferences", headers=headers, json=updated)
        self.assertEqual(save.status_code, 200)

        defaults = self.client.get("/api/v1/search/defaults?profile=default", headers=headers)
        self.assertEqual(defaults.status_code, 200)
        payload = defaults.json()
        self.assertEqual(payload["profile"], "workspace")
        self.assertEqual(payload["roles"], ["Teacher"])
        self.assertEqual(payload["locations"], ["Berlin, Germany"])
        self.assertEqual(payload["companies"], ["Khan Academy", "Coursera"])
        self.assertTrue(payload["include_linkedin_jobs"])
        self.assertEqual(payload["current_title"], "Teacher")
        self.assertEqual(payload["current_level"], "mid")
        self.assertEqual(payload["compensation_currency"], "EUR")
        self.assertEqual(payload["target_total_comp"], 65000)

        state = self.client.get("/api/v1/onboarding/state", headers=headers).json()
        self.assertEqual(state["workspace_id"], me["workspace"]["id"])

    def test_legacy_manual_place_is_normalized_in_defaults(self) -> None:
        headers = self._auth_headers()
        me = self.client.get("/api/v1/me", headers=headers).json()
        seeded = self.client.get("/api/v1/onboarding/state", headers=headers).json()["preferences"]
        save = self.client.post("/api/v1/onboarding/preferences", headers=headers, json=seeded)
        self.assertEqual(save.status_code, 200)

        db = self._get_db()
        record = self.workspace_service._get_workspace_preferences_record(db, me["workspace"]["id"])
        self.assertIsNotNone(record)
        record.preferred_places_json = json.dumps([
            {
                "label": "Los Angeles, CA",
                "kind": "manual",
                "city": "",
                "region": "",
                "country": "",
                "country_code": "",
                "lat": None,
                "lon": None,
                "provider": "manual",
                "provider_id": "",
            }
        ])
        db.commit()

        defaults = self.client.get("/api/v1/search/defaults?profile=default", headers=headers)
        self.assertEqual(defaults.status_code, 200)
        payload = defaults.json()
        self.assertEqual(payload["preferred_places"][0]["label"], "Los Angeles, CA")
        self.assertEqual(payload["preferred_places"][0]["match_scope"], "city")
        self.assertEqual(payload["preferred_places"][0]["city"], "Los Angeles")
        self.assertEqual(payload["preferred_places"][0]["region"], "CA")

    def test_analytics_stats_can_be_scoped_to_search_run(self) -> None:
        from app.models.application import ApplicationRecord

        headers = self._auth_headers()
        workspace_id = self.client.get("/api/v1/me", headers=headers).json()["workspace"]["id"]
        db = self._get_db()
        db.add_all([
            ApplicationRecord(
                job_title="Senior Data Engineer",
                company="Alpha",
                source="linkedin",
                recommendation="STRONG_APPLY",
                status="found",
                profile="workspace",
                workspace_id=workspace_id,
                search_run_id="run-new",
            ),
            ApplicationRecord(
                job_title="Analytics Engineer",
                company="Beta",
                source="builtin",
                recommendation="APPLY",
                status="applied",
                profile="workspace",
                workspace_id=workspace_id,
                search_run_id="run-old",
            ),
        ])
        db.commit()

        response = self.client.get("/api/v1/analytics/stats?search_run_id=run-new", headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_jobs"], 1)
        self.assertEqual(payload["strong_apply_count"], 1)
        self.assertEqual(payload["applied_count"], 0)

    def test_search_runs_are_workspace_scoped_and_worker_executes_durable_jobs(self) -> None:
        headers_a = self._auth_headers(user_id="user-a", email="user-a@example.com", full_name="User A")
        headers_b = self._auth_headers(user_id="user-b", email="user-b@example.com", full_name="User B")
        workspace_a = self.client.get("/api/v1/me", headers=headers_a).json()["workspace"]["id"]
        workspace_b = self.client.get("/api/v1/me", headers=headers_b).json()["workspace"]["id"]

        db = self._get_db()
        snapshot = self.workspace_service.build_search_snapshot(
            self.workspace_service.get_workspace_preferences(db, workspace_a)
        )
        self.workspace_service.register_search_run(
            db,
            workspace_a,
            "run-a",
            "pending",
            "search_score",
            snapshot,
            None,
            request_payload={
                "roles": ["Platform Engineer"],
                "keywords": ["AI"],
                "locations": ["Remote"],
                "companies": [],
                "include_remote": True,
                "workplace_preference": "remote_only",
                "max_days_old": 7,
                "use_ai": False,
                "profile": "workspace",
                "mode": "search_score",
            },
        )
        self.workspace_service.register_search_run(
            db,
            workspace_b,
            "run-b",
            "running",
            "search_score",
            snapshot,
            None,
            request_payload={},
        )
        self.workspace_service.append_search_event(
            db,
            workspace_b,
            "run-b",
            "progress",
            "already running elsewhere",
        )

        def fake_execute(run, roles, locations, *args, **kwargs):
            run.status = "completed"
            run.started_at = run.started_at or datetime.now(timezone.utc)
            run.completed_at = datetime.now(timezone.utc)
            run.jobs_found = 3
            run.jobs_scored = 2
            run.strong_matches = 1
            self.pipeline_service._send_event(run, "progress", f"searching {roles} in {locations}")
            self.pipeline_service._send_event(run, "complete", json.dumps({
                "run_id": run.run_id,
                "status": "completed",
                "jobs_found": 3,
                "jobs_scored": 2,
                "strong_matches": 1,
                "duration_seconds": 0.2,
                "error": None,
            }))
            self.pipeline_service._persist_workspace_run_status(run)

        with patch("app.services.pipeline_service._execute_pipeline", side_effect=fake_execute):
            processed = self.pipeline_service.process_next_hosted_run("worker-1")

        self.assertTrue(processed)

        runs_a = self.client.get("/api/v1/search/runs", headers=headers_a)
        self.assertEqual(runs_a.status_code, 200)
        self.assertEqual([item["run_id"] for item in runs_a.json()], ["run-a"])

        status_a = self.client.get("/api/v1/search/runs/run-a/status", headers=headers_a)
        self.assertEqual(status_a.status_code, 200)
        self.assertEqual(status_a.json()["status"], "completed")
        self.assertEqual(status_a.json()["jobs_found"], 3)
        self.assertEqual(
            status_a.json()["progress_messages"],
            [
                "Worker claimed run - starting search",
                "searching ['Platform Engineer', 'AI'] in ['Remote']",
            ],
        )

        blocked = self.client.get("/api/v1/search/runs/run-b/status", headers=headers_a)
        self.assertEqual(blocked.status_code, 404)

    def test_search_run_treats_remote_friendly_without_locations_as_remote_only(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        captured: dict[str, object] = {}

        def fake_start_run(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                run_id="run-remote-only",
                status="pending",
                started_at=None,
                completed_at=None,
            )

        with patch("app.services.pipeline_service.start_run", side_effect=fake_start_run):
            response = self.client.post(
                "/api/v1/search/run",
                headers=headers,
                json={
                    "roles": ["Staff Data Engineer"],
                    "locations": [],
                    "keywords": ["lakehouse"],
                    "companies": [],
                    "include_remote": True,
                    "workplace_preference": "remote_friendly",
                    "max_days_old": 14,
                    "use_ai": False,
                    "profile": "default",
                    "mode": "search_score",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run_id"], "run-remote-only")
        self.assertEqual(captured["workplace_preference"], "remote_only")
        self.assertEqual(captured["locations"], [])
        self.assertTrue(captured["include_remote"])

    def test_onboarding_search_treats_remote_friendly_without_locations_as_remote_only(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        captured: dict[str, object] = {}

        def fake_start_run(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                run_id="run-onboarding-remote-friendly",
                status="pending",
                started_at=None,
                completed_at=None,
            )

        with patch("app.services.pipeline_service.start_run", side_effect=fake_start_run):
            response = self.client.post(
                "/api/v1/onboarding/search",
                headers=headers,
                json={
                    "roles": ["Staff Data Engineer"],
                    "keywords": ["lakehouse"],
                    "companies": ["Stripe", "Databricks"],
                    "preferred_places": [],
                    "workplace_preference": "remote_friendly",
                    "max_days_old": 14,
                    "current_title": "Staff Data Engineer",
                    "current_level": "senior",
                    "compensation": {
                        "currency": "USD",
                        "pay_period": "annual",
                        "current_comp": None,
                        "min_base": None,
                        "target_total_comp": None,
                        "min_acceptable_tc": None,
                        "include_equity": True,
                    },
                    "exclude_staffing_agencies": True,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run_id"], "run-onboarding-remote-friendly")
        self.assertEqual(captured["workplace_preference"], "remote_only")
        self.assertEqual(captured["locations"], [])
        self.assertEqual(captured["companies"], ["Stripe", "Databricks"])
        self.assertTrue(captured["include_remote"])

    def test_onboarding_search_rejects_location_only_without_locations(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        response = self.client.post(
            "/api/v1/onboarding/search",
            headers=headers,
            json={
                "roles": ["Staff Data Engineer"],
                "keywords": ["lakehouse"],
                "companies": [],
                "preferred_places": [],
                "workplace_preference": "location_only",
                "max_days_old": 14,
                "current_title": "",
                "current_level": "senior",
                "compensation": {
                    "currency": "USD",
                    "pay_period": "annual",
                    "current_comp": None,
                    "min_base": None,
                    "target_total_comp": None,
                    "min_acceptable_tc": None,
                    "include_equity": True,
                },
                "exclude_staffing_agencies": True,
            },
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("Add at least one preferred location", response.text)

    def test_onboarding_state_not_ready_when_location_only_has_no_places(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)
        pdf_bytes = b"%PDF-1.4\nmock pdf payload"

        with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value="Experienced nurse practitioner"), patch(
            "app.services.resume_analyzer.analyze_resume",
            return_value={
                "suggested_target_roles": ["Nurse Practitioner"],
                "suggested_keywords": ["Primary Care"],
                "current_title": "Nurse Practitioner",
                "seniority": "senior",
            },
        ):
            upload = self.client.post(
                "/api/v1/onboarding/resume",
                headers=headers,
                files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
            )

        self.assertEqual(upload.status_code, 200, upload.text)
        prefs = upload.json()["analysis"]
        save = self.client.post(
            "/api/v1/onboarding/preferences",
            headers=headers,
            json={
                "roles": ["Nurse Practitioner"],
                "keywords": ["Primary Care"],
                "companies": [],
                "preferred_places": [],
                "workplace_preference": "location_only",
                "max_days_old": 14,
                "current_title": prefs["current_title"],
                "current_level": prefs["seniority"],
                "compensation": {
                    "currency": "USD",
                    "pay_period": "annual",
                    "current_comp": None,
                    "min_base": None,
                    "target_total_comp": None,
                    "min_acceptable_tc": None,
                    "include_equity": True,
                },
                "exclude_staffing_agencies": True,
            },
        )
        self.assertEqual(save.status_code, 200, save.text)

        state = self.client.get("/api/v1/onboarding/state", headers=headers)
        self.assertEqual(state.status_code, 200, state.text)
        payload = state.json()
        self.assertTrue(payload["resume"]["exists"])
        self.assertTrue(payload["needs_preferences"])
        self.assertFalse(payload["ready_to_search"])

    def test_search_run_derives_terms_from_workspace_resume_when_request_is_empty(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)
        pdf_bytes = b"%PDF-1.4\nmock pdf payload"

        with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value="Experienced nurse practitioner"), patch(
            "app.services.resume_analyzer.analyze_resume",
            return_value={
                "suggested_target_roles": [],
                "suggested_keywords": [],
                "current_title": "Nurse Practitioner",
                "seniority": "senior",
            },
        ):
            upload = self.client.post(
                "/api/v1/onboarding/resume",
                headers=headers,
                files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
            )
        self.assertEqual(upload.status_code, 200, upload.text)

        captured: dict[str, object] = {}

        def fake_start_run(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                run_id="run-resume-derived",
                status="pending",
                started_at=None,
                completed_at=None,
            )

        with patch("app.services.pipeline_service.start_run", side_effect=fake_start_run):
            response = self.client.post(
                "/api/v1/search/run",
                headers=headers,
                json={
                    "roles": [],
                    "locations": [],
                    "keywords": [],
                    "companies": [],
                    "include_remote": True,
                    "workplace_preference": "remote_friendly",
                    "max_days_old": 14,
                    "use_ai": False,
                    "profile": "default",
                    "mode": "search_score",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run_id"], "run-resume-derived")
        self.assertEqual(captured["roles"], ["Nurse Practitioner"])
        self.assertEqual(captured["keywords"], [])

    def test_search_suggest_times_out_falls_back_to_resume_terms(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        class FakeLLM:
            provider = "slow-provider"
            is_configured = True

        with patch("app.services.workspace_service.get_workspace_llm", return_value=FakeLLM()), patch(
            "app.services.workspace_service.get_resume_text",
            return_value="Experienced product manager resume text",
        ), patch(
            "app.api.search._get_fast_llm",
            return_value=(FakeLLM(), None),
        ), patch(
            "app.api.search._run_suggest_call",
            return_value=(None, "timeout"),
        ), patch(
            "app.services.workspace_service.derive_search_terms_from_resume",
            return_value=(["Product Manager"], ["roadmap"]),
        ):
            response = self.client.post("/api/v1/search/suggest?profile=workspace", headers=headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["roles"], ["Product Manager"])
        self.assertEqual(payload["keywords"], ["roadmap"])
        self.assertIn("fallback", payload["summary"].lower())

    def test_search_suggest_parse_failures_fall_back_to_resume_terms(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        class FakeLLM:
            provider = "broken-provider"
            is_configured = True

        with patch("app.services.workspace_service.get_workspace_llm", return_value=FakeLLM()), patch(
            "app.services.workspace_service.get_resume_text",
            return_value="Experienced product manager resume text",
        ), patch(
            "app.api.search._get_fast_llm",
            return_value=(FakeLLM(), None),
        ), patch(
            "app.api.search._run_suggest_call",
            return_value=(None, "parse"),
        ), patch(
            "app.services.workspace_service.derive_search_terms_from_resume",
            return_value=(["Staff Data Engineer"], ["lakehouse"]),
        ):
            response = self.client.post("/api/v1/search/suggest?profile=workspace", headers=headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["roles"], ["Staff Data Engineer"])
        self.assertEqual(payload["keywords"], ["lakehouse"])
        self.assertIn("unreadable", payload["summary"].lower())

    def test_search_suggest_falls_back_to_resume_terms_when_llm_omits_roles_and_keywords(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        class FakeLLM:
            provider = "gemini"
            is_configured = True

        with patch("app.services.workspace_service.get_workspace_llm", return_value=FakeLLM()), patch(
            "app.services.workspace_service.get_resume_text",
            return_value="Resume text",
        ), patch(
            "app.api.search._get_fast_llm",
            return_value=(FakeLLM(), None),
        ), patch(
            "app.api.search._run_suggest_call",
            return_value=(
                {
                    "roles": [],
                    "keywords": [],
                    "locations": ["Los Angeles, CA"],
                    "companies": ["Databricks"],
                    "summary": "Candidate summary",
                },
                None,
            ),
        ), patch(
            "app.services.workspace_service.derive_search_terms_from_resume",
            return_value=(["Data Platform Engineering Manager"], ["lakehouse"]),
        ):
            response = self.client.post("/api/v1/search/suggest?profile=workspace", headers=headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["roles"], ["Data Platform Engineering Manager"])
        self.assertEqual(payload["keywords"], ["lakehouse"])

    def test_search_run_derives_terms_from_word_per_line_resume_text(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)
        pdf_bytes = b"%PDF-1.4\nmock pdf payload"
        resume_text = "\n".join([
            "BRIAN",
            "TEH",
            "WORK",
            "EXPERIENCE",
            "B",
            "ILL",
            "Remote",
            "Manager",
            "(Lead),",
            "Data",
            "&",
            "Analytics",
            "Platform",
            "Engineering",
            "December",
            "2025",
            "Present",
        ])

        with patch("job_finder.tools.resume_parser_tool.parse_resume", return_value=resume_text), patch(
            "app.services.resume_analyzer.analyze_resume",
            return_value={
                "suggested_target_roles": [],
                "suggested_keywords": [],
                "current_title": "",
                "seniority": "senior",
            },
        ):
            upload = self.client.post(
                "/api/v1/onboarding/resume",
                headers=headers,
                files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
            )
        self.assertEqual(upload.status_code, 200, upload.text)

        captured: dict[str, object] = {}

        def fake_start_run(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                run_id="run-resume-word-lines",
                status="pending",
                started_at=None,
                completed_at=None,
            )

        with patch("app.services.pipeline_service.start_run", side_effect=fake_start_run):
            response = self.client.post(
                "/api/v1/search/run",
                headers=headers,
                json={
                    "roles": [],
                    "locations": [],
                    "keywords": [],
                    "companies": [],
                    "include_remote": True,
                    "workplace_preference": "remote_friendly",
                    "max_days_old": 14,
                    "use_ai": False,
                    "profile": "default",
                    "mode": "search_score",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["roles"], ["Manager (Lead), Data & Analytics Platform Engineering"])

    def test_hosted_search_run_reports_queued_state_before_worker_claim(self) -> None:
        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)
        db = self._get_db()
        self.workspace_service.update_worker_heartbeat(
            db,
            "worker-1",
            status="idle",
            metadata={"release": "test-release"},
        )

        response = self.client.post(
            "/api/v1/search/run",
            headers=headers,
            json={
                "roles": ["Data Engineer"],
                "locations": [],
                "keywords": ["lakehouse"],
                "companies": [],
                "include_remote": True,
                "workplace_preference": "remote_friendly",
                "max_days_old": 14,
                "use_ai": False,
                "profile": "default",
                "mode": "search_only",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        run_id = response.json()["run_id"]

        status = self.client.get(f"/api/v1/search/runs/{run_id}/status", headers=headers)
        self.assertEqual(status.status_code, 200, status.text)
        payload = status.json()
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["progress_messages"], ["Queued - waiting for an available worker"])

        db = self._get_db()
        events = self.workspace_service.list_search_events(
            db,
            self.client.get("/api/v1/me", headers=headers).json()["workspace"]["id"],
            run_id,
        )
        self.assertTrue(any(event.event_type == "stage" and "Queued for worker" in event.payload for event in events))

    def test_dev_hosted_search_runs_inline_when_worker_is_missing(self) -> None:
        os.environ["DEV_HOSTED_AUTH"] = "true"
        headers = self._auth_headers()
        workspace_id = self.client.get("/api/v1/me", headers=headers).json()["workspace"]["id"]

        def fake_submit(fn, *args, **kwargs):
            fn(*args, **kwargs)
            return SimpleNamespace()

        def fake_execute(run, roles, locations, *args, **kwargs):
            run.status = "completed"
            run.started_at = run.started_at or datetime.now(timezone.utc)
            run.completed_at = datetime.now(timezone.utc)
            run.jobs_found = 2
            run.jobs_scored = 2
            run.strong_matches = 1
            self.pipeline_service._send_event(run, "progress", f"inline search {roles} in {locations}")
            self.pipeline_service._send_event(run, "complete", json.dumps({
                "run_id": run.run_id,
                "status": "completed",
                "jobs_found": 2,
                "jobs_scored": 2,
                "strong_matches": 1,
                "duration_seconds": 0.1,
                "error": None,
            }))
            self.pipeline_service._persist_workspace_run_status(run)

        with patch.object(self.pipeline_service._executor, "submit", side_effect=fake_submit), patch(
            "app.services.pipeline_service._execute_pipeline",
            side_effect=fake_execute,
        ):
            response = self.client.post(
                "/api/v1/search/run",
                headers=headers,
                json={
                    "roles": ["Platform Engineer"],
                    "locations": [],
                    "keywords": ["AI"],
                    "companies": [],
                    "include_remote": True,
                    "workplace_preference": "remote_friendly",
                    "max_days_old": 7,
                    "use_ai": False,
                    "profile": "default",
                    "mode": "search_score",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        run_id = response.json()["run_id"]

        status = self.client.get(f"/api/v1/search/runs/{run_id}/status", headers=headers)
        self.assertEqual(status.status_code, 200, status.text)
        payload = status.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(
            payload["progress_messages"],
            [
                "Hosted sandbox worker unavailable - running inline for local development",
                "inline search ['Platform Engineer', 'AI'] in ['Remote']",
            ],
        )

        db = self._get_db()
        run = self.workspace_service.get_search_run(db, workspace_id, run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run.status, "completed")

    def test_dev_hosted_runtime_llm_does_not_inherit_global_env(self) -> None:
        os.environ["DEV_HOSTED_AUTH"] = "true"
        os.environ["HOSTED_ALLOW_WORKSPACE_LLM_CONFIG"] = "true"
        os.environ["LLM_PROVIDER"] = "custom"
        os.environ["LLM_BASE_URL"] = "http://localhost:8317/v1"
        os.environ["LLM_MODEL"] = "claude-opus-4-5-20251101"
        os.environ["LLM_API_KEY"] = "test-key"

        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        status = self.client.get("/api/v1/settings/llm", headers=headers)
        self.assertEqual(status.status_code, 200, status.text)
        payload = status.json()
        self.assertFalse(payload["configured"])
        self.assertTrue(payload["runtime_configurable"])

    def test_hosted_runtime_llm_requires_launchboard_secret(self) -> None:
        os.environ["HOSTED_ALLOW_WORKSPACE_LLM_CONFIG"] = "true"

        headers = self._auth_headers()
        self.client.get("/api/v1/me", headers=headers)

        missing_secret = self.client.put(
            "/api/v1/settings/llm",
            headers=headers,
            json={
                "provider": "openai-api",
                "base_url": "https://api.openai.com/v1",
                "api_key": "workspace-key",
                "model": "gpt-4o-mini",
            },
        )
        self.assertEqual(missing_secret.status_code, 503)
        self.assertIn("LAUNCHBOARD_SECRET", missing_secret.text)

        os.environ["LAUNCHBOARD_SECRET"] = "workspace-keys-need-a-stable-secret"
        saved = self.client.put(
            "/api/v1/settings/llm",
            headers=headers,
            json={
                "provider": "openai-api",
                "base_url": "https://api.openai.com/v1",
                "api_key": "workspace-key",
                "model": "gpt-4o-mini",
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)

    def test_platform_managed_ai_blocks_runtime_llm_mutation(self) -> None:
        headers = self._auth_headers()
        status = self.client.get("/api/v1/settings/llm", headers=headers)
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["runtime_configurable"])

        updated = self.client.put(
            "/api/v1/settings/llm",
            headers=headers,
            json={
                "provider": "openai-api",
                "base_url": "https://api.openai.com/v1",
                "api_key": "workspace-key",
                "model": "gpt-4o-mini",
            },
        )
        self.assertEqual(updated.status_code, 403)

        models = self.client.post(
            "/api/v1/settings/llm/models",
            headers=headers,
            json={"base_url": "https://api.openai.com/v1", "api_key": "test-key"},
        )
        self.assertEqual(models.status_code, 403)

    def test_prepare_and_apply_enforce_workspace_scope(self) -> None:
        headers_a = self._auth_headers(user_id="user-a", email="user-a@example.com", full_name="User A")
        headers_b = self._auth_headers(user_id="user-b", email="user-b@example.com", full_name="User B")
        workspace_a = self.client.get("/api/v1/me", headers=headers_a).json()["workspace"]["id"]
        self.client.get("/api/v1/me", headers=headers_b)

        from app.models.application import ApplicationRecord

        db = self._get_db()
        record = ApplicationRecord(
            job_title="Platform Engineer",
            company="Example Co",
            job_url="https://jobs.lever.co/example/abc123",
            workspace_id=workspace_a,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        prepare = self.client.post(f"/api/v1/applications/{record.id}/prepare", headers=headers_b)
        self.assertEqual(prepare.status_code, 404)

        apply = self.client.post(
            f"/api/v1/applications/{record.id}/apply",
            headers=headers_b,
            json={"dry_run": True, "cover_letter": ""},
        )
        self.assertEqual(apply.status_code, 404)

    def test_worker_health_reflects_recent_heartbeats(self) -> None:
        db = self._get_db()
        self.workspace_service.update_worker_heartbeat(
            db,
            "worker-1",
            status="busy",
            metadata={"release": "test-release"},
        )

        response = self.client.get("/health/worker")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["workers"][0]["worker_id"], "worker-1")
        self.assertTrue(payload["workers"][0]["compatible"])


if __name__ == "__main__":
    unittest.main()
