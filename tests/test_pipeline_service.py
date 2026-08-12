from __future__ import annotations

import importlib
import sys
import unittest
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
if BACKEND_PATH in sys.path:
    sys.path.remove(BACKEND_PATH)
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class PipelineServiceTimeTest(unittest.TestCase):
    def setUp(self) -> None:
        for module_name in list(sys.modules):
            if module_name == "app.services.pipeline_service" or module_name.startswith("app.services.pipeline_service."):
                sys.modules.pop(module_name, None)
        self.pipeline_service = importlib.import_module("app.services.pipeline_service")

    def test_coerce_utc_preserves_naive_datetimes_as_utc(self) -> None:
        naive = datetime(2026, 3, 23, 12, 0, 0)
        coerced = self.pipeline_service._coerce_utc(naive)

        self.assertIsNotNone(coerced)
        self.assertEqual(coerced.tzinfo, timezone.utc)
        self.assertEqual(coerced.hour, 12)

    def test_coerce_utc_normalizes_aware_datetimes(self) -> None:
        aware = datetime(2026, 3, 23, 12, 0, 0, tzinfo=timezone.utc)
        coerced = self.pipeline_service._coerce_utc(aware)

        self.assertEqual(coerced, aware)

    def test_execute_pipeline_preserves_structured_preferred_places(self) -> None:
        captured: dict[str, object] = {}

        class FakePipeline:
            def __init__(self) -> None:
                self.profile_name = "workspace"
                self.llm = None
                self.config = {
                    "search_settings": {"ai_score_top_n": 60},
                    "location_preferences": {
                        "preferred_places": [
                            {
                                "label": "Los Angeles, CA",
                                "kind": "city",
                                "match_scope": "city",
                                "city": "Los Angeles",
                                "region": "CA",
                                "country": "United States",
                                "country_code": "US",
                            }
                        ],
                        "preferred_locations": ["Los Angeles, CA"],
                        "preferred_states": ["CA"],
                        "preferred_cities": ["Los Angeles"],
                    },
                    "scoring": {"thresholds": {"strong_apply": 70}},
                }

            def run_full_pipeline(self, **kwargs):
                captured["location_preferences"] = self.config["location_preferences"]
                captured["locations"] = self.config["locations"]
                return []

        run = self.pipeline_service.PipelineRun(
            run_id="run123",
            profile="workspace",
            mode="search_score",
        )

        with patch("app.services.pipeline_service.get_pipeline", return_value=FakePipeline()), patch(
            "app.services.pipeline_service._auto_deduplicate",
            return_value=0,
        ):
            self.pipeline_service._execute_pipeline(
                run,
                roles=["data engineer"],
                locations=["Los Angeles, CA", "Remote"],
                use_ai=True,
                mode="search_score",
                workplace_preference="remote_friendly",
                config_override={
                    "location_preferences": {
                        "preferred_places": [
                            {
                                "label": "Los Angeles, CA",
                                "kind": "city",
                                "match_scope": "city",
                                "city": "Los Angeles",
                                "region": "CA",
                                "country": "United States",
                                "country_code": "US",
                            }
                        ],
                        "preferred_locations": ["Los Angeles, CA"],
                        "preferred_states": ["CA"],
                        "preferred_cities": ["Los Angeles"],
                    }
                },
            )

        location_preferences = captured["location_preferences"]
        self.assertIsInstance(location_preferences, dict)
        self.assertEqual(location_preferences["preferred_places"][0]["match_scope"], "city")
        self.assertEqual(location_preferences["preferred_places"][0]["city"], "Los Angeles")
        self.assertEqual(location_preferences["preferred_cities"], ["Los Angeles"])
        self.assertEqual(captured["locations"], ["Los Angeles, CA", "Remote"])

    def test_start_run_requires_compatible_hosted_worker(self) -> None:
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)

        settings = SimpleNamespace(
            hosted_mode=True,
            dev_hosted_auth_enabled=False,
            resolved_app_release="test-release",
        )

        with patch("app.services.pipeline_service.get_settings", return_value=settings), patch(
            "app.services.pipeline_service._has_compatible_hosted_worker",
            return_value=False,
        ):
            with self.assertRaises(RuntimeError):
                self.pipeline_service.start_run(
                    roles=["data engineer"],
                    locations=["Los Angeles, CA"],
                    keywords=[],
                    include_remote=True,
                    max_days_old=14,
                    use_ai=True,
                    profile="workspace",
                    mode="search_score",
                    loop=loop,
                    workspace_id="ws_123",
                )


class StartRunIdempotentTest(unittest.TestCase):
    """A second start_run for a workspace that already has an active run must
    return the existing run, not raise — so the user's re-click after a page
    refresh lands on the in-progress search instead of getting a 409 toast.
    """

    def setUp(self) -> None:
        backend_path = str(Path(__file__).resolve().parents[1] / "backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        import importlib

        self.pipeline_service = importlib.import_module("app.services.pipeline_service")
        # Save + restore the module-level _runs dict so we don't leak state.
        self._original_runs = dict(self.pipeline_service._runs)
        self.pipeline_service._runs.clear()

    def tearDown(self) -> None:
        self.pipeline_service._runs.clear()
        self.pipeline_service._runs.update(self._original_runs)

    def _seed_active_run(self, workspace_id: str, run_id: str = "existing-run"):
        run = self.pipeline_service.PipelineRun(
            run_id=run_id,
            profile="workspace",
            mode="search_score",
            workspace_id=workspace_id,
            status="running",
            queue=None,
            loop=None,
        )
        self.pipeline_service._runs[run_id] = run
        return run

    def test_start_run_returns_existing_run_when_workspace_has_active_run(self) -> None:
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        seeded = self._seed_active_run("ws_dup", "abc123")

        settings = SimpleNamespace(
            hosted_mode=False,
            dev_hosted_auth_enabled=False,
            resolved_app_release="test-release",
        )
        with patch("app.services.pipeline_service.get_settings", return_value=settings):
            result = self.pipeline_service.start_run(
                roles=["data engineer"],
                locations=["Remote"],
                keywords=[],
                include_remote=True,
                max_days_old=30,
                use_ai=False,
                profile="workspace",
                mode="search_score",
                loop=loop,
                workspace_id="ws_dup",
            )

        # Must return the SAME run (no error, no new spawn) — that's how the
        # frontend joins the in-progress search seamlessly.
        self.assertIs(result, seeded)
        self.assertEqual(result.run_id, "abc123")
        # And the in-memory registry must not gain a second entry for this workspace.
        ws_runs = [r for r in self.pipeline_service._runs.values() if r.workspace_id == "ws_dup"]
        self.assertEqual(len(ws_runs), 1, "Idempotent start_run must not spawn a duplicate")

    def test_start_run_creates_new_run_when_existing_one_completed(self) -> None:
        """Completed/failed runs in _runs must not block a new search."""
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        seeded = self._seed_active_run("ws_done", "old-run")
        seeded.status = "completed"

        settings = SimpleNamespace(
            hosted_mode=False,
            dev_hosted_auth_enabled=False,
            resolved_app_release="test-release",
        )
        # Mock the executor so we don't actually run the pipeline thread —
        # we only care that start_run created a fresh PipelineRun and didn't
        # reuse the completed one.
        with patch("app.services.pipeline_service.get_settings", return_value=settings), \
             patch.object(self.pipeline_service._executor, "submit"):
            result = self.pipeline_service.start_run(
                roles=["data engineer"],
                locations=["Remote"],
                keywords=[],
                include_remote=True,
                max_days_old=30,
                use_ai=False,
                profile="workspace",
                mode="search_score",
                loop=loop,
                workspace_id="ws_done",
            )

        self.assertIsNot(result, seeded, "Completed run must not be reused")
        self.assertEqual(result.status, "pending")
        self.assertNotEqual(result.run_id, "old-run")

    def test_start_run_does_not_collide_across_workspaces(self) -> None:
        """An active run for workspace A must not block workspace B."""
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        self._seed_active_run("ws_a", "run-a")

        settings = SimpleNamespace(
            hosted_mode=False,
            dev_hosted_auth_enabled=False,
            resolved_app_release="test-release",
        )
        with patch("app.services.pipeline_service.get_settings", return_value=settings), \
             patch.object(self.pipeline_service._executor, "submit"):
            result = self.pipeline_service.start_run(
                roles=["data engineer"],
                locations=["Remote"],
                keywords=[],
                include_remote=True,
                max_days_old=30,
                use_ai=False,
                profile="workspace",
                mode="search_score",
                loop=loop,
                workspace_id="ws_b",
            )
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.workspace_id, "ws_b")
        self.assertNotEqual(result.run_id, "run-a")

    def test_durable_run_persists_effective_remote_location_and_does_not_execute_inline(self) -> None:
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        captured: dict[str, object] = {}
        settings = SimpleNamespace(
            hosted_mode=False,
            dev_hosted_auth_enabled=False,
            resolved_app_release="test-release",
        )

        def fake_register(_db, _workspace_id, _run_id, _status, _mode, _snapshot, _started_at, *, request_payload):
            captured.update(request_payload)

        with patch("app.services.pipeline_service.get_settings", return_value=settings), \
             patch("app.services.pipeline_service._with_db", side_effect=lambda callback: callback(object())), \
             patch("app.services.workspace_service.get_active_search_run", return_value=None), \
             patch("app.services.workspace_service.register_search_run", side_effect=fake_register), \
             patch.object(self.pipeline_service._executor, "submit") as submit:
            result = self.pipeline_service.start_run(
                roles=["data engineer"],
                locations=["Los Angeles, CA"],
                keywords=[],
                include_remote=True,
                workplace_preference="remote_friendly",
                max_days_old=30,
                use_ai=False,
                profile="workspace",
                mode="search_only",
                loop=loop,
                workspace_id="ws_durable",
                snapshot=object(),
                durable=True,
            )

        self.assertEqual(captured["locations"], ["Los Angeles, CA", "Remote"])
        self.assertEqual(result.status, "pending")
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
