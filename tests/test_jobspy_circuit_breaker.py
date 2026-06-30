"""Contract tests for the per-board JobSpy circuit breaker.

JobSpy doesn't ship a fail-fast knob, so when one of its scrapers (Indeed,
Glassdoor, ZipRecruiter, Google, LinkedIn) starts failing — 429 CAPTCHA,
Cloudflare 403, parse errors — every query burns ~30 retries before
giving up. Across a typical 30-query search that's minutes of wasted time.

These tests pin the breaker's contract:

1. ``ERROR`` logs from ``JobSpy:<Board>`` increment that board's failure
   counter, and once the counter hits ``_FAILURE_THRESHOLD`` the circuit
   opens for ``_DISABLE_DURATION_S`` seconds.
2. While a board is circuit-open, ``_filter_active_boards`` excludes it.
3. ``search_jobs`` skips disabled boards before calling ``scrape_jobs``;
   if ALL requested boards are disabled, it short-circuits to ``[]``
   without hitting the library at all.
4. A board that produces ≥1 row in the response DataFrame resets its
   failure counter (self-healing).
5. The handler is idempotent on re-import (uvicorn --reload doesn't
   stack-attach handlers).
"""

from __future__ import annotations

import importlib
import logging
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class CircuitBreakerTest(unittest.TestCase):
    """Failure counting, threshold-based circuit open, TTL expiry, reset on success."""

    def setUp(self) -> None:
        self.mod = importlib.import_module("job_finder.tools.job_search_tool")
        self.mod.reset_circuit()
        # pytest may have cleared root handlers between tests — re-install
        # ours so the logger-based assertions stay green regardless of test
        # ordering.
        self.mod._install_jobspy_error_handler()

    def tearDown(self) -> None:
        self.mod.reset_circuit()

    def test_single_error_does_not_open_circuit(self) -> None:
        self.mod._record_board_failure("google")
        self.assertFalse(self.mod._is_board_disabled("google"))

    def test_threshold_errors_open_circuit(self) -> None:
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("google")
        self.assertTrue(self.mod._is_board_disabled("google"))

    def test_other_boards_unaffected_when_one_opens(self) -> None:
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("google")
        self.assertTrue(self.mod._is_board_disabled("google"))
        self.assertFalse(self.mod._is_board_disabled("indeed"))
        self.assertFalse(self.mod._is_board_disabled("linkedin"))

    def test_case_insensitive_board_names(self) -> None:
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("Google")
        self.assertTrue(self.mod._is_board_disabled("google"))
        self.assertTrue(self.mod._is_board_disabled("GOOGLE"))

    def test_filter_active_boards_splits_correctly(self) -> None:
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("google")
        active, skipped = self.mod._filter_active_boards(
            ["indeed", "google", "linkedin"]
        )
        self.assertEqual(active, ["indeed", "linkedin"])
        self.assertEqual(skipped, ["google"])

    def test_ttl_expires_and_board_becomes_active_again(self) -> None:
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("google")
        # Fast-forward time past the disable window.
        with patch.object(self.mod.time, "time", return_value=time.time() + self.mod._DISABLE_DURATION_S + 1):
            self.assertFalse(self.mod._is_board_disabled("google"))

    def test_failures_within_window_open_circuit(self) -> None:
        """Threshold failures clustered in time still open the circuit."""
        base = time.time()
        with patch.object(self.mod.time, "time", return_value=base):
            for _ in range(self.mod._FAILURE_THRESHOLD):
                self.mod._record_board_failure("indeed")
            self.assertTrue(self.mod._is_board_disabled("indeed"))

    def test_failures_spread_past_window_do_not_open_circuit(self) -> None:
        """The real user bug: a few transient errors spread across a run must
        NOT black out the only board. Failures older than the rolling window
        age out, so they can't accumulate to the threshold."""
        base = time.time()
        # threshold-1 failures at t0
        with patch.object(self.mod.time, "time", return_value=base):
            for _ in range(self.mod._FAILURE_THRESHOLD - 1):
                self.mod._record_board_failure("indeed")
        # one more failure AFTER the window has elapsed — the old ones expired,
        # so the counter restarts and the circuit stays closed.
        with patch.object(
            self.mod.time, "time",
            return_value=base + self.mod._FAILURE_WINDOW_S + 1,
        ):
            self.mod._record_board_failure("indeed")
            self.assertFalse(self.mod._is_board_disabled("indeed"))

    def test_success_resets_failure_counter(self) -> None:
        # Accumulate failures but not enough to open the circuit.
        for _ in range(self.mod._FAILURE_THRESHOLD - 1):
            self.mod._record_board_failure("google")
        # A successful scrape returning google rows should clear the counter.
        df = pd.DataFrame([{"site": "google", "title": "Engineer"}])
        self.mod._record_board_success(["google", "indeed"], df)
        # Now adding more failures should NOT immediately open the circuit:
        # counter started fresh.
        self.mod._record_board_failure("google")
        self.assertFalse(self.mod._is_board_disabled("google"))

    def test_handler_increments_counter_from_jobspy_logger(self) -> None:
        """JobSpy:* ERROR logs feed the breaker."""
        jobspy_log = logging.getLogger("JobSpy:Google")
        # Three ERROR logs from JobSpy:Google → circuit open.
        for _ in range(self.mod._FAILURE_THRESHOLD):
            jobspy_log.error("Google response status code 429 /sorry/index")
        self.assertTrue(self.mod._is_board_disabled("google"))

    def test_handler_ignores_warn_and_info(self) -> None:
        jobspy_log = logging.getLogger("JobSpy:Indeed")
        for _ in range(self.mod._FAILURE_THRESHOLD * 2):
            jobspy_log.warning("transient slowness")
            jobspy_log.info("retrying")
        self.assertFalse(self.mod._is_board_disabled("indeed"))

    def test_handler_ignores_non_jobspy_loggers(self) -> None:
        other = logging.getLogger("some.other.module")
        for _ in range(self.mod._FAILURE_THRESHOLD * 2):
            other.error("not a JobSpy logger")
        self.assertFalse(self.mod._is_board_disabled("indeed"))

    def test_handler_install_is_idempotent(self) -> None:
        """uvicorn --reload re-imports the module — we must not stack handlers."""
        before = len(logging.getLogger("JobSpy").handlers)
        self.mod._install_jobspy_error_handler()
        self.mod._install_jobspy_error_handler()
        after = len(logging.getLogger("JobSpy").handlers)
        self.assertEqual(before, after)


class SearchJobsCircuitBreakerIntegrationTest(unittest.TestCase):
    """End-to-end: search_jobs skips disabled boards and short-circuits."""

    def setUp(self) -> None:
        self.mod = importlib.import_module("job_finder.tools.job_search_tool")
        self.mod.reset_circuit()

    def tearDown(self) -> None:
        self.mod.reset_circuit()

    def test_search_jobs_skips_disabled_board(self) -> None:
        # Open the circuit for Google.
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("google")

        captured_kwargs: dict = {}

        def fake_scrape_jobs(**kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame([
                {"site": "indeed", "title": "Engineer", "company": "Acme",
                 "location": "Remote", "is_remote": True, "job_url": "https://x",
                 "company_name": "Acme", "description": "", "date_posted": ""},
            ])

        with patch.dict(
            sys.modules,
            {"jobspy": MagicMock(scrape_jobs=fake_scrape_jobs)},
        ):
            results = self.mod.search_jobs(
                search_term="data engineer",
                boards=["indeed", "google"],
            )

        self.assertGreaterEqual(len(results), 1)
        # google should have been removed before scrape_jobs was called
        self.assertEqual(captured_kwargs.get("site_name"), ["indeed"])

    def test_search_jobs_returns_empty_when_all_boards_disabled(self) -> None:
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("google")
        for _ in range(self.mod._FAILURE_THRESHOLD):
            self.mod._record_board_failure("indeed")

        sentinel = MagicMock(name="scrape_jobs_must_not_be_called")

        with patch.dict(
            sys.modules,
            {"jobspy": MagicMock(scrape_jobs=sentinel)},
        ):
            results = self.mod.search_jobs(
                search_term="data engineer",
                boards=["indeed", "google"],
            )

        self.assertEqual(results, [])
        sentinel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
