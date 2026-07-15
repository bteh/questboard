"""Contract tests for the 1iota TV-audience scraper (audience kind).

Fixture is a trimmed REAL response from
https://prod-tickets.1iota.com/api/event/list (captured live 2026-07-08,
HTTP 200, 143 events; 5 representative events kept). Pins the quest-row
contract: deep-link URL, event_start from the taping datetime (Z and no-Z
forms), unpaid rows never carry salary keys, sold-out events are skipped,
first_quest_ok, quest extras, and registry metadata (vertical audience,
disabled by default). No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "oneiota_events.json"


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class OneIotaParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import oneiota as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_oneiota(**kw)

    def test_parses_fixture_events(self) -> None:
        rows = self._search(_load_fixture())
        # 5 fixture events, 1 sold out (LIVE with Kelly & Mark) is skipped.
        self.assertEqual(len(rows), 4)
        daily = rows[0]
        self.assertEqual(daily["title"], "Audience seat: The Daily Show")
        self.assertEqual(daily["company"], "1iota")
        self.assertEqual(daily["source"], "1iota")
        self.assertEqual(daily["vertical"], "audience")
        self.assertEqual(daily["url"], "https://1iota.com/event/88956")
        self.assertEqual(daily["location"], "New York, NY")

    def test_sold_out_events_are_skipped(self) -> None:
        rows = self._search(_load_fixture())
        self.assertFalse(any("Kelly" in r["title"] for r in rows))

    def test_event_start_from_taping_datetime_with_z(self) -> None:
        rows = self._search(_load_fixture())
        daily = rows[0]
        self.assertEqual(daily["event_start"], "2026-07-29T20:30:00+00:00")

    def test_event_start_without_z_suffix_still_utc(self) -> None:
        rows = self._search(_load_fixture())
        seth = next(r for r in rows if "Seth Meyers" in r["title"])
        self.assertEqual(seth["event_start"], "2026-07-30T18:00:00+00:00")

    def test_unpaid_rows_never_carry_salary_or_date_posted(self) -> None:
        # The SuperFan event's description mentions a $200 gift card; that
        # prose must never become pay, and the API states no posting date.
        rows = self._search(_load_fixture())
        for row in rows:
            for key in ("salary_min", "salary_max", "salary_period",
                        "salary_source", "date_posted"):
                self.assertNotIn(key, row)

    def test_first_quest_ok_and_quest_extras(self) -> None:
        rows = self._search(_load_fixture())
        daily = rows[0]
        self.assertTrue(daily["first_quest_ok"])
        self.assertEqual(daily["quest"]["show"], "The Daily Show")
        self.assertEqual(daily["quest"]["city"], "New York")
        self.assertEqual(daily["quest"]["age_min"], 18)
        self.assertEqual(daily["quest"]["max_tickets"], 2)
        self.assertNotIn("coming_soon", daily["quest"])

    def test_coming_soon_flagged_in_quest(self) -> None:
        rows = self._search(_load_fixture())
        match_day = next(r for r in rows if "Match Day" in r["title"])
        self.assertTrue(match_day["quest"]["coming_soon"])

    def test_virtual_event_keeps_anywhere_location(self) -> None:
        rows = self._search(_load_fixture())
        superfan = next(r for r in rows if "SuperFan" in r["title"])
        self.assertEqual(superfan["location"], "Anywhere")
        self.assertNotIn("state", superfan["quest"])

    def test_entity_escaped_description_is_stripped(self) -> None:
        rows = self._search(_load_fixture())
        daily = rows[0]
        self.assertIn("Jon Stewart", daily["description"])
        self.assertNotIn("&lt;", daily["description"])
        self.assertNotIn("<p", daily["description"])

    def test_subtitle_appends_to_title(self) -> None:
        events = _load_fixture()
        kelly = next(e for e in events if e["eventId"] == 89603)
        row = self.mod._normalize_event(kelly)
        self.assertEqual(
            row["title"], "Audience seat: LIVE with Kelly & Mark (DOWNTOWN LOCATION)",
        )

    def test_max_results_caps_output(self) -> None:
        rows = self._search(_load_fixture(), max_results=2)
        self.assertEqual(len(rows), 2)

    def test_skips_events_missing_id_or_title(self) -> None:
        events = _load_fixture()
        events[0]["eventId"] = None
        events[1]["title"] = "  "
        rows = self._search(events)
        self.assertEqual(len(rows), 2)  # 2 dropped + 1 sold out of 5

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, "nope", 42):
            self.assertEqual(self._search(bad), [])
        self.assertEqual(self._search([]), [])
        self.assertEqual(self._search(["nope", 3]), [])

    def test_duplicate_event_ids_deduped(self) -> None:
        events = _load_fixture()
        rows = self._search(events + events)
        urls = [r["url"] for r in rows]
        self.assertEqual(len(urls), len(set(urls)))


class OneIotaRegistryTest(unittest.TestCase):
    def test_registered_as_audience_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.oneiota  # noqa: F401
        reg = get_registry()
        self.assertIn("1iota", reg)
        meta = reg["1iota"]
        self.assertEqual(meta.vertical, "audience")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_never_in_default_career_sweep(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401  (triggers registration)
        from job_finder.tools.scrapers._registry import default_scraper_names
        self.assertNotIn("1iota", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
