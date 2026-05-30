"""Workday must use a tight per-request timeout like the other ATS scrapers.

Bug: Workday's _TIMEOUT was 20s (vs 5s for Ashby/Lever/Greenhouse) on BOTH the
search POST and the serial per-posting detail GET. One hung enterprise tenant
could blow past the 60s per-scraper registry cap and get abandoned while
orphaned requests kept tying up a pool worker. Workday is all big-enterprise
tenants (zero crypto/startup relevance) yet shares the pool budget.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import workday

_EMPLOYER = {"base_url": "https://x.wd1.myworkdayjobs.com", "tenant": "t", "site_id": "s", "name": "X"}

_MAX_TIMEOUT = 8


class _FakeResp:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"jobPostingInfo": {}}


class WorkdayTimeoutTest(unittest.TestCase):
    def test_detail_get_uses_tight_timeout(self) -> None:
        captured: dict = {}

        def fake_get(url, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return _FakeResp()

        with patch.object(workday.requests, "get", fake_get):
            workday._api_detail(_EMPLOYER, "/job/1")
        self.assertIsNotNone(captured.get("timeout"))
        self.assertLessEqual(captured["timeout"], _MAX_TIMEOUT)

    def test_search_post_uses_tight_timeout(self) -> None:
        captured: dict = {}

        def fake_post(url, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            return _FakeResp()

        with patch.object(workday.requests, "post", fake_post):
            workday._api_search(_EMPLOYER, "engineer", limit=10)
        self.assertIsNotNone(captured.get("timeout"))
        self.assertLessEqual(captured["timeout"], _MAX_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
