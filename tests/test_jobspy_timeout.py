"""search_jobs must bound each scrape_jobs call with a wall-clock deadline.

Bug: the JobSpy pool had no per-task timeout (unlike the additional-scrapers
thread's 120s join). A slow/hung board — google is CAPTCHA-prone and the
default — stalled a worker until JobSpy internally gave up (minutes), and the
per-board breaker only helps on the NEXT call, not the first slow one.
"""

from __future__ import annotations

import importlib
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class JobSpyTimeoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = importlib.import_module("job_finder.tools.job_search_tool")
        self.mod.reset_circuit()

    def tearDown(self) -> None:
        self.mod.reset_circuit()

    def test_slow_scrape_times_out_returns_empty_and_records_failure(self) -> None:
        def slow_scrape_jobs(**kwargs):
            time.sleep(2.0)
            return pd.DataFrame()

        start = time.monotonic()
        with patch.dict(sys.modules, {"jobspy": MagicMock(scrape_jobs=slow_scrape_jobs)}):
            results = self.mod.search_jobs(
                search_term="data engineer",
                boards=["google"],
                scrape_timeout=0.3,
            )
        elapsed = time.monotonic() - start

        self.assertEqual(results, [])
        self.assertLess(elapsed, 1.5)  # returned well before the 2s sleep
        with self.mod._BOARD_CIRCUIT_LOCK:
            failures = self.mod._BOARD_CIRCUIT.get("google", {}).get("failures", 0)
        self.assertGreaterEqual(failures, 1)  # fed the breaker proactively

    def test_fast_scrape_within_timeout_returns_results(self) -> None:
        def fast_scrape_jobs(**kwargs):
            return pd.DataFrame([
                {"site": "google", "title": "Engineer", "company": "Acme",
                 "location": "Remote", "is_remote": True, "job_url": "https://x",
                 "company_name": "Acme", "description": "", "date_posted": ""},
            ])

        with patch.dict(sys.modules, {"jobspy": MagicMock(scrape_jobs=fast_scrape_jobs)}):
            results = self.mod.search_jobs(
                search_term="data engineer",
                boards=["google"],
                scrape_timeout=10,
            )
        self.assertGreaterEqual(len(results), 1)

    def test_no_timeout_argument_preserves_legacy_behavior(self) -> None:
        def fast_scrape_jobs(**kwargs):
            return pd.DataFrame([
                {"site": "indeed", "title": "Engineer", "company": "Acme",
                 "location": "Remote", "is_remote": True, "job_url": "https://x",
                 "company_name": "Acme", "description": "", "date_posted": ""},
            ])

        with patch.dict(sys.modules, {"jobspy": MagicMock(scrape_jobs=fast_scrape_jobs)}):
            results = self.mod.search_jobs(search_term="data engineer", boards=["indeed"])
        self.assertGreaterEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
