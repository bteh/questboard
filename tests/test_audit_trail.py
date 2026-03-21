"""Tests for settings audit trail (Issue #9).

Verifies that saving settings produces a log entry with old and new values,
and that only changed fields are recorded in the diff.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import yaml

# ── Import gymnastics ──
# The root-level app.py (legacy) shadows `backend/app/` when both
# `src` and the project root are on sys.path.  Force-import the backend
# `app` package.
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))

for p in (_backend_dir, _src_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

if "app" in sys.modules:
    del sys.modules["app"]

_app_init = os.path.join(_backend_dir, "app", "__init__.py")
_spec = importlib.util.spec_from_file_location(
    "app", _app_init,
    submodule_search_locations=[os.path.join(_backend_dir, "app")],
)
_app_mod = importlib.util.module_from_spec(_spec)
sys.modules["app"] = _app_mod
_spec.loader.exec_module(_app_mod)

_svc_init = os.path.join(_backend_dir, "app", "services", "__init__.py")
_svc_spec = importlib.util.spec_from_file_location(
    "app.services", _svc_init,
    submodule_search_locations=[os.path.join(_backend_dir, "app", "services")],
)
_svc_mod = importlib.util.module_from_spec(_svc_spec)
sys.modules["app.services"] = _svc_mod
_svc_spec.loader.exec_module(_svc_mod)

_ss_path = os.path.join(_backend_dir, "app", "services", "settings_service.py")
_ss_spec = importlib.util.spec_from_file_location("app.services.settings_service", _ss_path)
settings_service = importlib.util.module_from_spec(_ss_spec)
sys.modules["app.services.settings_service"] = settings_service
_ss_spec.loader.exec_module(settings_service)


class AuditTrailTest(unittest.TestCase):
    """Test audit logging in settings_service.update_profile_preferences."""

    def setUp(self) -> None:
        """Create a temporary directory with a template and profile YAML."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_root = self.tmpdir.name

        # Create the profile directory structure
        self.config_dir = os.path.join(
            self.project_root, "src", "job_finder", "config", "profiles",
        )
        os.makedirs(self.config_dir, exist_ok=True)

        # Create a data directory for the audit log
        self.data_dir = os.path.join(self.project_root, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        # Write a template profile
        template = {
            "profile": {"name": "Template", "description": "Template profile"},
            "career_baseline": {
                "current_title": "Engineer",
                "current_level": "mid",
                "current_tc": 100_000,
            },
            "compensation": {
                "min_base": 80_000,
                "target_total_comp": 150_000,
            },
        }
        with open(os.path.join(self.config_dir, "_template.yaml"), "w") as f:
            yaml.dump(template, f)

        # Write an existing test profile
        self.profile_data = {
            "profile": {"name": "Test User", "description": "Test profile"},
            "career_baseline": {
                "current_title": "Software Engineer",
                "current_level": "mid",
                "current_tc": 120_000,
            },
            "compensation": {
                "min_base": 100_000,
                "target_total_comp": 180_000,
            },
        }
        with open(os.path.join(self.config_dir, "test.yaml"), "w") as f:
            yaml.dump(self.profile_data, f)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_settings_change_logged(self) -> None:
        """Saving settings should produce a log entry with old and new values."""
        with (
            patch.object(settings_service, "_PROJECT_ROOT", self.project_root),
            patch.object(settings_service, "get_config") as mock_get_config,
        ):
            # get_config returns the *updated* profile data (called after write)
            mock_get_config.return_value = {
                "career_baseline": {
                    "current_title": "Senior Software Engineer",
                    "current_level": "senior",
                    "current_tc": 150_000,
                },
                "compensation": {
                    "min_base": 120_000,
                    "target_total_comp": 200_000,
                },
            }

            with self.assertLogs("app.services.settings_service", level="INFO") as cm:
                settings_service.update_profile_preferences(
                    "test",
                    {
                        "current_title": "Senior Software Engineer",
                        "current_level": "senior",
                        "current_tc": 150_000,
                        "min_base": 120_000,
                        "target_total_comp": 200_000,
                    },
                )

            # Verify log messages contain change information
            log_output = "\n".join(cm.output)
            self.assertIn("Settings changed", log_output)

    def test_audit_trail_records_diff(self) -> None:
        """Only changed fields should be recorded in the diff."""
        with (
            patch.object(settings_service, "_PROJECT_ROOT", self.project_root),
            patch.object(settings_service, "get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {
                "career_baseline": {
                    "current_title": "Software Engineer",
                    "current_level": "mid",
                    "current_tc": 120_000,
                },
                "compensation": {
                    "min_base": 120_000,
                    "target_total_comp": 180_000,
                },
            }

            with self.assertLogs("app.services.settings_service", level="INFO") as cm:
                settings_service.update_profile_preferences(
                    "test",
                    {
                        "current_title": "Software Engineer",
                        "current_level": "mid",
                        "current_tc": 120_000,
                        "min_base": 120_000,
                        "target_total_comp": 180_000,
                    },
                )

            log_output = "\n".join(cm.output)
            # min_base changed from 100_000 to 120_000, should appear in diff
            self.assertIn("min_base", log_output)

    def test_audit_trail_written_to_file(self) -> None:
        """When settings change, a JSON line should be appended to the audit log."""
        with (
            patch.object(settings_service, "_PROJECT_ROOT", self.project_root),
            patch.object(settings_service, "get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {
                "career_baseline": {
                    "current_title": "Staff Engineer",
                    "current_level": "staff",
                    "current_tc": 200_000,
                },
                "compensation": {
                    "min_base": 150_000,
                    "target_total_comp": 250_000,
                },
            }

            settings_service.update_profile_preferences(
                "test",
                {
                    "current_title": "Staff Engineer",
                    "current_level": "staff",
                    "current_tc": 200_000,
                    "min_base": 150_000,
                    "target_total_comp": 250_000,
                },
            )

        audit_path = os.path.join(self.data_dir, "settings_audit.log")
        self.assertTrue(
            os.path.exists(audit_path),
            "Audit log file should be created",
        )

        with open(audit_path, "r") as f:
            lines = [line.strip() for line in f if line.strip()]

        self.assertGreaterEqual(len(lines), 1, "At least one audit entry should exist")
        entry = json.loads(lines[-1])
        self.assertIn("profile", entry)
        self.assertIn("changes", entry)
        self.assertIn("timestamp", entry)

    def test_no_audit_when_nothing_changed(self) -> None:
        """When no fields changed, no audit entry should be written."""
        with (
            patch.object(settings_service, "_PROJECT_ROOT", self.project_root),
            patch.object(settings_service, "get_config") as mock_get_config,
        ):
            mock_get_config.return_value = {
                "career_baseline": {
                    "current_title": "Software Engineer",
                    "current_level": "mid",
                    "current_tc": 120_000,
                },
                "compensation": {
                    "min_base": 100_000,
                    "target_total_comp": 180_000,
                },
            }

            settings_service.update_profile_preferences(
                "test",
                {
                    "current_title": "Software Engineer",
                    "current_level": "mid",
                    "current_tc": 120_000,
                    "min_base": 100_000,
                    "target_total_comp": 180_000,
                },
            )

        audit_path = os.path.join(self.data_dir, "settings_audit.log")
        if os.path.exists(audit_path):
            with open(audit_path, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
            self.assertEqual(len(lines), 0, "No audit entries for unchanged settings")


if __name__ == "__main__":
    unittest.main()
