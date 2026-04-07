from __future__ import annotations

import importlib
import sys
import unittest
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


class WorkerLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        for module_name in list(sys.modules):
            if module_name == "app.worker" or module_name.startswith("app.worker."):
                sys.modules.pop(module_name, None)
        self.worker = importlib.import_module("app.worker")

    def test_worker_loop_marks_error_and_keeps_running(self) -> None:
        settings = SimpleNamespace(
            resolved_database_url="sqlite:////tmp/launchboard-worker-test.db",
            data_dir="/tmp/launchboard-worker-test",
            worker_poll_interval_seconds=0.01,
            worker_id="worker-test",
            resolved_app_release="test-release",
        )
        statuses: list[str] = []

        with patch("app.worker.get_settings", return_value=settings), patch(
            "app.worker.init_db",
        ), patch(
            "app.worker._tick_heartbeat",
            side_effect=lambda status: statuses.append(status),
        ), patch(
            "app.worker.pipeline_service.process_next_hosted_run",
            side_effect=[RuntimeError("boom"), KeyboardInterrupt],
        ), patch("app.worker.time.sleep"):
            with self.assertRaises(KeyboardInterrupt):
                self.worker.main()

        self.assertEqual(statuses, ["running", "error", "running"])

    def test_worker_heartbeat_includes_release_metadata(self) -> None:
        settings = SimpleNamespace(
            worker_id="worker-test",
            resolved_app_release="test-release",
        )

        with patch("app.worker.get_settings", return_value=settings), patch(
            "app.worker.get_db",
        ) as get_db, patch(
            "app.worker.workspace_service.update_worker_heartbeat",
        ) as update_worker_heartbeat:
            db = object()
            get_db.return_value = iter([db])
            self.worker._tick_heartbeat("idle")

        update_worker_heartbeat.assert_called_once()
        _, kwargs = update_worker_heartbeat.call_args
        self.assertEqual(kwargs["metadata"]["release"], "test-release")


if __name__ == "__main__":
    unittest.main()
