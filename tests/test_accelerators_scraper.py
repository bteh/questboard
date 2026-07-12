"""Contract tests for the accelerator-majors scraper (pitch kind).

Fixtures are trimmed REAL captures from the three curated pages (probed
live 2026-07-12, all HTTP 200): the YC /apply data-page div verbatim, the
Techstars __NEXT_DATA__ trimmed to two real programs (nyc open with a
final_deadline, boston concluded), and the raw region around the 500
Global flagship sentence. Pins: the YC row incl. year roll-forward, the
Techstars open-status gate + deadline mapping + past-deadline drop, the
500 strict-grammar-or-skip rule, per-page failure isolation, no salary
keys anywhere, the cap, and registration. No live HTTP inside tests.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURES = ROOT / "tests" / "fixtures"
YC_HTML = (FIXTURES / "yc_apply.html").read_text(encoding="utf-8")
TECHSTARS_HTML = (FIXTURES / "techstars_accelerators.html").read_text(encoding="utf-8")
FIVEHUNDRED_HTML = (FIXTURES / "500_flagship.html").read_text(encoding="utf-8")

# the live probe date; nyc's real final_deadline (2026-06-10) is before it
PROBE_DAY = date(2026, 7, 12)
# a frozen day before the Techstars deadline so the open window is testable
EARLY_DAY = date(2026, 5, 1)


class _Resp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self._status = status

    def raise_for_status(self) -> None:
        if self._status >= 400:
            raise RuntimeError(f"HTTP {self._status}")


def _route(overrides: dict | None = None):
    """A requests.get side_effect serving the fixtures, keyed by host."""
    pages = {
        "ycombinator.com": _Resp(YC_HTML),
        "techstars.com": _Resp(TECHSTARS_HTML),
        "500.co": _Resp(FIVEHUNDRED_HTML),
    }
    pages.update(overrides or {})

    def get(url, **kwargs):
        for host, resp in pages.items():
            if host in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"unexpected URL fetched: {url}")

    return get


class AcceleratorsSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import accelerators as mod
        self.mod = mod

    def _search(self, today: date, overrides: dict | None = None, **kw) -> list[dict]:
        with patch.object(self.mod.requests, "get", side_effect=_route(overrides)), \
                patch.object(self.mod, "_today", return_value=today):
            return self.mod.search_accelerators(**kw)

    def _by_company(self, rows: list[dict]) -> dict:
        out: dict = {}
        for row in rows:
            out.setdefault(row["company"], []).append(row)
        return out

    def test_yc_row_from_data_page(self) -> None:
        rows = self._by_company(self._search(PROBE_DAY))["Y Combinator"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Y Combinator Fall 2026 batch")
        self.assertEqual(row["url"], "https://apply.ycombinator.com/home")
        self.assertEqual(row["source"], "accelerators")
        self.assertEqual(row["vertical"], "pitch")
        # "July 27" has no year; July 27 is ahead of the probe day
        self.assertEqual(row["quest"]["apply_by"], "2026-07-27")

    def test_yc_deadline_rolls_forward_when_passed(self) -> None:
        rows = self._by_company(self._search(date(2026, 8, 15)))["Y Combinator"]
        self.assertEqual(rows[0]["quest"]["apply_by"], "2027-07-27")

    def test_yc_deadline_same_day_does_not_roll(self) -> None:
        rows = self._by_company(self._search(date(2026, 7, 27)))["Y Combinator"]
        self.assertEqual(rows[0]["quest"]["apply_by"], "2026-07-27")

    def test_techstars_open_gate_and_deadline_mapping(self) -> None:
        rows = self._by_company(self._search(EARLY_DAY))["Techstars"]
        # boston ("Accelerator Concluded") must not emit; nyc must
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Techstars New York City Accelerator")
        self.assertEqual(row["url"], "https://apply.techstars.com?accelerator=nyc")
        self.assertEqual(row["quest"]["apply_by"], "2026-06-10")
        self.assertEqual(row["date_posted"], "2026-03-02")
        self.assertEqual(row["vertical"], "pitch")

    def test_techstars_past_deadline_dropped(self) -> None:
        # on the probe day nyc's stated deadline has passed even though the
        # page still says "Now Reviewing Applications"
        by_company = self._by_company(self._search(PROBE_DAY))
        self.assertNotIn("Techstars", by_company)

    def test_500_strict_grammar_match(self) -> None:
        rows = self._by_company(self._search(PROBE_DAY))["500 Global"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "500 Global Flagship Accelerator Batch 36")
        self.assertEqual(row["url"], "https://500.co/founders/flagship")
        self.assertEqual(row["quest"]["apply_by"], "2026-10-11")
        self.assertEqual(
            row["description"],
            "Applications close October 11th for Flagship Accelerator Batch 36.",
        )

    def test_500_no_match_emits_nothing(self) -> None:
        variants = (
            "<html><body>Applications close soon for Flagship Accelerator Batch 36.</body></html>",
            "<html><body>Applications close October 11th for the next batch.</body></html>",
            "<html><body>nothing here</body></html>",
        )
        for html in variants:
            rows = self._search(PROBE_DAY, overrides={"500.co": _Resp(html)})
            self.assertNotIn("500 Global", self._by_company(rows), html)

    def test_page_failure_does_not_kill_the_others(self) -> None:
        import requests as requests_lib

        for broken in ("ycombinator.com", "techstars.com", "500.co"):
            for failure in (_Resp("oops", status=500),
                            requests_lib.exceptions.ConnectionError("down")):
                rows = self._search(EARLY_DAY, overrides={broken: failure})
                companies = set(self._by_company(rows))
                expected = {"Y Combinator", "Techstars", "500 Global"}
                survivors = {
                    "ycombinator.com": "Y Combinator",
                    "techstars.com": "Techstars",
                    "500.co": "500 Global",
                }
                self.assertEqual(companies, expected - {survivors[broken]})

    def test_no_salary_keys_anywhere(self) -> None:
        rows = self._search(EARLY_DAY)
        self.assertEqual(len(rows), 3)
        for row in rows:
            for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
                self.assertNotIn(key, row, row["title"])

    def test_max_results_cap(self) -> None:
        rows = self._search(EARLY_DAY, max_results=1)
        self.assertEqual(len(rows), 1)

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        import job_finder.tools.scrapers  # noqa: F401 (trigger auto-discovery)
        meta = get_registry()["accelerators"]
        rows = self._search(EARLY_DAY)
        valid, rejected = validate_rows(rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), 3)


class AcceleratorsRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401 (trigger auto-discovery)
        from job_finder.tools.scrapers._registry import default_scraper_names, get_registry

        meta = get_registry()["accelerators"]
        self.assertEqual(meta.display_name, "Accelerator majors")
        self.assertEqual(meta.vertical, "pitch")
        self.assertEqual(meta.refresh_hours, 168)
        self.assertTrue(meta.full_snapshot)
        self.assertIsNone(meta.stale_after_days)
        self.assertEqual(
            meta.allowed_url_hosts, ("ycombinator.com", "techstars.com", "500.co")
        )
        self.assertFalse(meta.enabled_by_default)
        self.assertFalse(meta.research_only)
        self.assertNotIn("accelerators", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
