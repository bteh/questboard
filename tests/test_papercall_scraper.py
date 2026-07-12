"""Contract tests for the PaperCall event-directory scraper (speak kind).

Fixture is trimmed from the REAL https://www.papercall.io/events capture
(live-probed 2026-07-12, HTTP 200): three cards from page 1 plus
ServerlessDays Cardiff from page 2 (the only travel-flag card with an
open CFP in the capture), all kept verbatim. Tests freeze the clock at
2026-07-28T00:00:00Z, between two real deadlines, so OWASP New Zealand
Day (closed 2026-07-25) is the past-deadline drop while Cardiff
(2026-07-31) stays. No live HTTP inside tests.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "papercall_events.html"

# between the OWASP close (07-25) and the Cardiff close (07-31)
FROZEN_NOW = datetime(2026, 7, 28, tzinfo=timezone.utc)

_SALARY_KEYS = ("salary_min", "salary_max", "salary_period", "salary_source")


def _parse_cards(html: str) -> list:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser").select("div.event-list-detail")


class PapercallParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import papercall as mod
        self.mod = mod
        self.cards = _parse_cards(FIXTURE.read_text(encoding="utf-8"))

    def _search(self, pages: list[list], **kw) -> list[dict]:
        with patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW), \
                patch.object(self.mod, "_fetch_page", side_effect=[*pages, []]), \
                patch.object(self.mod.time, "sleep"):
            return self.mod.search_papercall(**kw)

    def test_parses_cards_into_speak_rows(self) -> None:
        # 4 fixture cards: the past-deadline card and the deadline-less
        # open card both drop; only provably-live CFPs publish
        rows = self._search([self.cards])
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["vertical"], "speak")
            self.assertEqual(row["source"], "papercall")
            self.assertTrue(row["url"].startswith("https://www.papercall.io/"))
            self.assertTrue(row["title"])

    def test_card_to_row_mapping(self) -> None:
        rows = self._search([self.cards])
        row = next(r for r in rows if r["url"].endswith("/productivityconference"))
        self.assertEqual(row["title"], "Speak at AI Coding Summit: London, New York, Berlin")
        self.assertEqual(row["quest"]["apply_by"], "2026-08-12T23:59:00Z")
        self.assertEqual(row["quest"]["event_dates"], "July 06, 2026, July 07, 2026")
        self.assertEqual(
            row["location"], "London & Online, New York & Online, Berlin & Online"
        )

    def test_travel_flag_is_pay_note_never_salary(self) -> None:
        rows = self._search([self.cards])
        cardiff = next(r for r in rows if r["url"].endswith("/sls-days-cardiff-2026"))
        self.assertEqual(
            cardiff["quest"]["pay_note"], "CFP offers travel assistance (as stated)"
        )
        for row in rows:
            for key in _SALARY_KEYS:
                self.assertNotIn(key, row)

    def test_past_deadline_row_dropped(self) -> None:
        rows = self._search([self.cards])
        self.assertNotIn(
            "https://www.papercall.io/owaspnz26", [r["url"] for r in rows]
        )

    def test_open_cfp_without_deadline_never_publishes(self) -> None:
        # "CFP is open" with no close time is the recurring-meetup class
        # whose pages outlive the event: a 2020 conference wore that
        # label on the live board (2026-07-12). Only a future close time
        # proves liveness.
        rows = self._search([self.cards])
        self.assertFalse(
            any(r["url"].endswith("/stripe-meetup-london") for r in rows)
        )


class PapercallPaginationTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import papercall as mod
        self.mod = mod
        self.cards = _parse_cards(FIXTURE.read_text(encoding="utf-8"))

    def _full_page(self, n: int = 20) -> list:
        # n distinct-slug clones of the real future-deadline card:
        # pagination/cap mechanics only, the card HTML itself is verbatim
        card_html = next(
            str(c) for c in self.cards if "productivityconference" in str(c)
        )
        page_html = "".join(
            card_html.replace("productivityconference", f"productivityconference-{i}")
            for i in range(n)
        )
        return _parse_cards(page_html)

    def test_pagination_stops_on_short_page(self) -> None:
        fetch = MagicMock(side_effect=[self._full_page(20), self.cards[:3]])
        with patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW), \
                patch.object(self.mod, "_fetch_page", fetch), \
                patch.object(self.mod.time, "sleep"):
            self.mod.search_papercall(max_results=1000)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual([c.args[0] for c in fetch.call_args_list], [1, 2])

    def test_max_results_cap(self) -> None:
        fetch = MagicMock(return_value=self._full_page(20))
        with patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW), \
                patch.object(self.mod, "_fetch_page", fetch), \
                patch.object(self.mod.time, "sleep") as slept:
            rows = self.mod.search_papercall(max_results=7)
        self.assertEqual(len(rows), 7)
        self.assertEqual(fetch.call_count, 1)
        slept.assert_not_called()

    def test_sleep_called_between_pages(self) -> None:
        fetch = MagicMock(side_effect=[self._full_page(20), self.cards[:3]])
        with patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW), \
                patch.object(self.mod, "_fetch_page", fetch), \
                patch.object(self.mod.time, "sleep") as slept:
            self.mod.search_papercall(max_results=1000)
        slept.assert_called_once_with(self.mod._PAGE_SLEEP)


class PapercallFetchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import papercall as mod
        self.mod = mod

    def test_bad_html_returns_empty(self) -> None:
        resp = MagicMock(text="<html><body>not the directory</body>", url=self.mod._EVENTS_URL)
        resp.raise_for_status.return_value = None
        with patch.object(self.mod.requests, "get", return_value=resp):
            self.assertEqual(self.mod.search_papercall(), [])

    def test_fetch_error_returns_empty(self) -> None:
        with patch.object(self.mod.requests, "get", side_effect=OSError("boom")):
            self.assertEqual(self.mod.search_papercall(), [])

    def test_fetch_asks_for_html(self) -> None:
        captured: dict = {}

        def fake_get(url, params=None, headers=None, timeout=None):
            captured["accept"] = (headers or {}).get("Accept", "")
            captured["params"] = params
            resp = MagicMock(text="<html></html>")
            resp.raise_for_status.return_value = None
            return resp

        with patch.object(self.mod.requests, "get", side_effect=fake_get):
            self.mod._fetch_page(3)
        self.assertEqual(captured["accept"], "text/html")
        self.assertEqual(captured["params"], {"page": 3})


class PapercallRegistryTest(unittest.TestCase):
    def test_registry_contract(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401 — triggers discovery
        from job_finder.tools.scrapers._registry import (
            default_scraper_names,
            get_registry,
        )

        meta = get_registry()["papercall"]
        self.assertEqual(meta.vertical, "speak")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("papercall.io",))
        self.assertFalse(meta.enabled_by_default)
        self.assertNotIn("papercall", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
