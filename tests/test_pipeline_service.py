"""Tests for pipeline_service — strong match threshold from config."""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# ── Import gymnastics ──
# The root-level app.py (legacy) shadows `backend/app/` when both
# `src` and the project root are on sys.path.  We need to force-import
# the *backend* `app` package before the legacy module gets loaded.
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))

# Prepend backend so `app` resolves to `backend/app/` (a package dir)
# and remove the project root / cwd if present.
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (_backend_dir, _src_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# If the root-level `app` module was already imported (from pytest collecting),
# replace it with the backend package.
if "app" in sys.modules:
    del sys.modules["app"]

# Now import the backend app package from backend/
import importlib.util

_app_init = os.path.join(_backend_dir, "app", "__init__.py")
_spec = importlib.util.spec_from_file_location("app", _app_init, submodule_search_locations=[os.path.join(_backend_dir, "app")])
_app_mod = importlib.util.module_from_spec(_spec)
sys.modules["app"] = _app_mod
_spec.loader.exec_module(_app_mod)

# Import the services subpackage
_svc_init = os.path.join(_backend_dir, "app", "services", "__init__.py")
_svc_spec = importlib.util.spec_from_file_location("app.services", _svc_init, submodule_search_locations=[os.path.join(_backend_dir, "app", "services")])
_svc_mod = importlib.util.module_from_spec(_svc_spec)
sys.modules["app.services"] = _svc_mod
_svc_spec.loader.exec_module(_svc_mod)

# Now import the target module
_ps_path = os.path.join(_backend_dir, "app", "services", "pipeline_service.py")
_ps_spec = importlib.util.spec_from_file_location("app.services.pipeline_service", _ps_path)
pipeline_service = importlib.util.module_from_spec(_ps_spec)
sys.modules["app.services.pipeline_service"] = pipeline_service
_ps_spec.loader.exec_module(pipeline_service)

PipelineRun = pipeline_service.PipelineRun
_execute_pipeline = pipeline_service._execute_pipeline


class StrongMatchThresholdTest(unittest.TestCase):
    """Issue #4: _STRONG_MATCH_THRESHOLD hardcoded instead of reading from config."""

    @patch.object(pipeline_service, "get_pipeline")
    @patch.object(pipeline_service, "_auto_deduplicate", return_value=0)
    def test_strong_matches_uses_config_threshold(
        self, mock_dedup: MagicMock, mock_get_pipeline: MagicMock,
    ) -> None:
        """When profile sets strong_apply to 50, jobs scoring 55 should count
        as strong matches (would be missed with hardcoded 70)."""
        mock_pipeline = MagicMock()
        mock_pipeline.config = {
            "scoring": {
                "thresholds": {"strong_apply": 50},
            },
        }
        mock_pipeline.profile_name = "test"
        mock_pipeline.run_full_pipeline.return_value = [
            {"title": "Eng A", "overall_score": 55},
            {"title": "Eng B", "overall_score": 45},
            {"title": "Eng C", "overall_score": 75},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        run = PipelineRun(
            run_id="test123",
            profile="test",
            mode="search_score",
        )
        run.queue = None
        run.loop = None

        _execute_pipeline(run, ["engineer"], ["Remote"], use_ai=True, mode="search_score")

        # With threshold 50: scores 55 and 75 are strong matches -> 2
        # With hardcoded 70: only 75 -> 1
        self.assertEqual(run.strong_matches, 2)

    @patch.object(pipeline_service, "get_pipeline")
    @patch.object(pipeline_service, "_auto_deduplicate", return_value=0)
    def test_default_threshold_is_70(
        self, mock_dedup: MagicMock, mock_get_pipeline: MagicMock,
    ) -> None:
        """When config has no thresholds section, default to 70."""
        mock_pipeline = MagicMock()
        mock_pipeline.config = {}
        mock_pipeline.profile_name = "test"
        mock_pipeline.run_full_pipeline.return_value = [
            {"title": "Eng A", "overall_score": 65},
            {"title": "Eng B", "overall_score": 75},
        ]
        mock_get_pipeline.return_value = mock_pipeline

        run = PipelineRun(
            run_id="test456",
            profile="test",
            mode="search_score",
        )
        run.queue = None
        run.loop = None

        _execute_pipeline(run, ["engineer"], ["Remote"], use_ai=True, mode="search_score")

        # Default threshold 70: only 75 qualifies -> 1
        self.assertEqual(run.strong_matches, 1)


if __name__ == "__main__":
    unittest.main()
