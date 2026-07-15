"""Contract tests for the Devpost hackathons scraper (pitch kind).

Fixture is 6 trimmed REAL hackathons captured live 2026-07-15 from
https://devpost.com/api/hackathons?status[]=open&status[]=upcoming&order_by=prize-amount
(HTTP 200, meta.total_count 165). The six cover the cases that matter:
USD, rupee, and euro prizes (verbatim rendering), same-month and
cross-month date ranges, open and upcoming states, and one invite_only
gig that must be excluded. Pins: invite_only drops, the prize renders
verbatim in the description and never as salary, rows point at
devpost.com, a concrete end date becomes event_start (else is_rolling),
and the fetch uses a browser UA that never names an AI. No live HTTP.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "devpost_hackathons.json"


def _page() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class DevpostTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import devpost as mod
        self.mod = mod

    def _search(self, **kw) -> list[dict]:
        # one page (6 items < per_page) so the loop stops after page 1
        with patch.object(self.mod, "_fetch_page", return_value=_page()):
            return self.mod.search_devpost(**kw)

    def test_publishes_the_non_invite_hackathons(self) -> None:
        rows = self._search()
        # 6 fixture items, the one invite_only gig drops
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row["source"], "devpost")
            self.assertEqual(row["vertical"], "pitch")
            self.assertEqual(row["company"], "Devpost")
            self.assertTrue(row["first_quest_ok"])

    def test_invite_only_is_excluded(self) -> None:
        titles = [r["title"] for r in self._search()]
        self.assertNotIn(
            "SMU .Hack Enrichment Application Programme 2026", titles
        )

    def test_prize_is_verbatim_in_description_never_salary(self) -> None:
        rows = self._search()
        by_title = {r["title"]: r for r in rows}
        xprize = by_title["Build with Gemini XPRIZE"]
        # the prize leads the description so the scannable card line carries it
        self.assertTrue(xprize["description"].startswith("$2,000,000 in prizes."))
        self.assertEqual(xprize["quest"]["prize"], "$2,000,000")
        # a rupee prize renders exactly as Devpost displays it
        galuxium = by_title["Galuxium Nexus V2"]
        self.assertTrue(galuxium["description"].startswith("₹ 100,000 in prizes."))
        # a euro prize too
        rect = by_title["RecT Solutions Hackathon: Beyond the CV 2026"]
        self.assertTrue(rect["description"].startswith("€2,000 in prizes."))
        # the prize never leaks into the salary fields
        for row in rows:
            self.assertIsNone(row["salary_min"], row["title"])
            self.assertIsNone(row["salary_max"], row["title"])

    def test_rows_point_at_devpost(self) -> None:
        from urllib.parse import urlsplit

        for row in self._search():
            host = urlsplit(row["url"]).netloc
            self.assertTrue(
                host == "devpost.com" or host.endswith(".devpost.com"),
                row["url"],
            )

    def test_concrete_end_date_becomes_event_start(self) -> None:
        rows = self._search()
        by_title = {r["title"]: r for r in rows}
        # cross-month range: end month carries its own name
        self.assertEqual(
            by_title["Build with Gemini XPRIZE"]["event_start"], "2026-08-17"
        )
        # same-month range: the end day inherits the start month
        self.assertEqual(
            by_title["OpenAI Build Week"]["event_start"], "2026-07-21"
        )
        self.assertEqual(
            by_title["Galuxium Nexus V2"]["event_start"], "2026-08-01"
        )
        # every fixture row has a dated window, so none rides as rolling
        for row in rows:
            self.assertIn("event_start", row, row["title"])
            self.assertNotIn("is_rolling", row)

    def test_timing_string_is_kept_verbatim(self) -> None:
        rows = self._search()
        by_title = {r["title"]: r for r in rows}
        self.assertEqual(
            by_title["OpenAI Build Week"]["quest"]["timing"], "Jul 13 - 21, 2026"
        )

    def test_undated_window_rides_as_rolling(self) -> None:
        item = {
            "title": "Some rolling jam",
            "url": "https://rolling-jam.devpost.com/",
            "organization_name": "Someone",
            "prize_amount": "$<span data-currency-value>500</span>",
            "submission_period_dates": "",
            "invite_only": False,
        }
        row = self.mod._normalize(item)
        self.assertIsNotNone(row)
        self.assertTrue(row["is_rolling"])
        self.assertNotIn("event_start", row)
        self.assertNotIn("timing", row["quest"])

    def test_prize_text_strips_the_span_flush(self) -> None:
        self.assertEqual(
            self.mod._prize_text("$<span data-currency-value>100,000</span>"),
            "$100,000",
        )
        self.assertEqual(self.mod._prize_text(None), "")

    def test_parse_end_date_edges(self) -> None:
        self.assertEqual(
            self.mod._parse_end_date("May 19 - Aug 17, 2026").isoformat(),
            "2026-08-17",
        )
        self.assertEqual(
            self.mod._parse_end_date("Jul 13 - 21, 2026").isoformat(),
            "2026-07-21",
        )
        self.assertEqual(
            self.mod._parse_end_date("Jul 18, 2026").isoformat(), "2026-07-18"
        )
        self.assertIsNone(self.mod._parse_end_date(""))
        self.assertIsNone(self.mod._parse_end_date("sometime soon"))

    def test_no_em_dashes_anywhere(self) -> None:
        for row in self._search():
            values = list(row.values()) + list(row["quest"].values())
            for value in values:
                if isinstance(value, str):
                    self.assertNotIn("—", value, row["title"])

    def test_max_results_caps_rows(self) -> None:
        self.assertEqual(len(self._search(max_results=2)), 2)
        self.assertEqual(self._search(max_results=0), [])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["devpost"]
        valid, rejected = validate_rows(self._search(), meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), 5)

    def test_fetch_uses_a_browser_ua_and_names_no_ai(self) -> None:
        captured: dict = {}

        class _Resp:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return _page()

        def fake_get(url, params=None, headers=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers or {}
            return _Resp()

        with patch.object(self.mod.requests, "get", side_effect=fake_get):
            self.mod.search_devpost()

        self.assertEqual(captured["url"], self.mod._API_URL)
        ua = captured["headers"].get("User-Agent", "")
        self.assertIn("Mozilla", ua)
        self.assertNotIn("anthropic", ua.lower())
        # the query targets open + upcoming, ranked by prize
        flat = captured["params"]
        self.assertIn(("status[]", "open"), flat)
        self.assertIn(("status[]", "upcoming"), flat)
        self.assertIn(("order_by", "prize-amount"), flat)


class DevpostRegistryTest(unittest.TestCase):
    def test_registered_as_pitch_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.devpost  # noqa: F401

        reg = get_registry()
        self.assertIn("devpost", reg)
        meta = reg["devpost"]
        self.assertEqual(meta.vertical, "pitch")
        self.assertEqual(meta.display_name, "Devpost hackathons")
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        self.assertEqual(meta.refresh_hours, 24)
        self.assertEqual(meta.stale_after_days, 14)
        self.assertFalse(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("devpost.com",))
        self.assertTrue(callable(meta.search_fn))
        # quest scrapers never join the default career sweep
        self.assertNotIn("devpost", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
