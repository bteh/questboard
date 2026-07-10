"""Contract tests for the User Interviews scraper (think kind).

Fixture is a trimmed REAL response from
https://www.userinterviews.com/api/project_listings (captured live
2026-07-09, HTTP 200, JSON:API) plus two edge variants (isPrivate,
noIncentive). Pins: private and unpaid listings never surface, the
stated per-session compensation maps exactly, the gift-card incentive
string reaches the description verbatim, and study run windows map to
event_end only (a study mid-window is still joinable). No live HTTP
inside tests.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "userinterviews_listings.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class UserInterviewsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import userinterviews as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_userinterviews(**kw)

    def test_private_and_unpaid_listings_never_surface(self) -> None:
        rows = self._search(_load_fixture())
        # 6 fixture listings: the isPrivate and noIncentive variants drop
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row["vertical"], "think")
            self.assertTrue(row["url"].startswith("https://www.userinterviews.com/"))

    def test_stated_session_pay_maps_exactly(self) -> None:
        rows = self._search(_load_fixture())
        flight = next(r for r in rows if "Flight Centre" in r["title"])
        self.assertEqual(flight["salary_min"], 45.0)
        self.assertEqual(flight["salary_max"], 45.0)
        self.assertEqual(flight["salary_period"], "session")
        self.assertEqual(flight["salary_source"], "reported")

    def test_gift_card_incentive_is_disclosed_up_front(self) -> None:
        rows = self._search(_load_fixture())
        flight = next(r for r in rows if "Flight Centre" in r["title"])
        self.assertIn("gift card", flight["description"].lower())
        self.assertIn("gift card", flight["quest"]["pay_note"].lower())

    def test_run_window_maps_to_event_end_only(self) -> None:
        rows = self._search(_load_fixture())
        dated = [r for r in rows if r.get("event_end")]
        self.assertTrue(dated, "at least one fixture listing carries a run window")
        self.assertIsInstance(dated[0]["event_end"], datetime)
        for row in rows:
            self.assertNotIn("event_start", row)

    def test_online_listings_read_as_remote(self) -> None:
        rows = self._search(_load_fixture())
        online = [r for r in rows if r["is_remote"]]
        self.assertTrue(online)
        self.assertEqual(online[0]["location"], "Remote")

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, {"data": None}, "x", 42):
            self.assertEqual(self._search(bad), [])


if __name__ == "__main__":
    unittest.main()
