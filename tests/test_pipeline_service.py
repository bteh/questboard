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


if __name__ == "__main__":
    unittest.main()
