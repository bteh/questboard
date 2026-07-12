"""Contract tests for the SBIR.gov open-topics scraper (pitch kind).

Fixtures are trimmed REAL pages captured live 2026-07-12: three listing
blocks from https://www.sbir.gov/topics?keywords=&status=Open&page=1 and
the detail page for topic 12563 (HHS parent SBIR grant), both kept
verbatim. Pins: listing blocks map to pitch rows anchored at sbir.gov,
the detail page supplies the funding agency as counterparty and the
official-solicitation link, close date becomes quest.apply_by and
past-deadline rows drop, pay renders only as a stated ceiling, and
pagination plus max_results stay polite. No live HTTP inside tests.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

LISTING = (ROOT / "tests" / "fixtures" / "sbir_topics.html").read_text(encoding="utf-8")
DETAIL = (ROOT / "tests" / "fixtures" / "sbir_topic_detail.html").read_text(encoding="utf-8")

# the fixture rows close 2026-08-19; the detail's schedule closes 2027-04-06
NOW_OPEN = datetime(2026, 7, 12, tzinfo=timezone.utc)
NOW_LATE = datetime(2026, 9, 1, tzinfo=timezone.utc)


class _Resp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHTTP:
    """Routes listing pages and detail URLs; counts every request."""

    def __init__(self, pages: dict[int, str] | None = None, detail: str | None = DETAIL):
        self.pages = pages if pages is not None else {0: LISTING}
        self.detail = detail
        self.listing_calls: list[int] = []
        self.detail_calls: list[str] = []

    def get(self, url, headers=None, timeout=None):
        if "/topics?" in url:
            page = int(url.rsplit("page=", 1)[1])
            self.listing_calls.append(page)
            return _Resp(self.pages.get(page, "<html><body></body></html>"))
        self.detail_calls.append(url)
        if self.detail is None:
            return _Resp("", status=404)
        return _Resp(self.detail)


class SbirSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import sbir as mod
        self.mod = mod

    def _search(self, http: _FakeHTTP, now: datetime = NOW_OPEN, **kw) -> list[dict]:
        with patch.object(self.mod.requests, "get", side_effect=http.get), \
                patch.object(self.mod.time, "sleep"), \
                patch.object(self.mod, "_utcnow", return_value=now):
            return self.mod.search_sbir(**kw)

    def test_listing_blocks_map_to_pitch_rows(self) -> None:
        # detail 404s so this pins pure listing-level mapping
        rows = self._search(_FakeHTTP(detail=None))
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["vertical"], "pitch")
        self.assertEqual(first["source"], "sbir")
        self.assertEqual(first["url"], "https://www.sbir.gov/topics/12837")
        self.assertTrue(first["title"].startswith("Collaborative Aided Target Recognition"))
        self.assertEqual(first["company"], "DOD")  # the agency seal, pre-detail
        self.assertEqual(first["date_posted"], "2026-07-01")  # release date
        self.assertIn("unmanned platforms", first["description"])
        self.assertEqual(first["quest"]["apply_by"], "2026-08-19")
        self.assertEqual(first["quest"]["program"], "STTR")
        self.assertEqual(first["quest"]["phase"], "BOTH")
        self.assertEqual(rows[1]["quest"]["program"], "SBIR")

    def test_detail_enriches_agency_and_official_link(self) -> None:
        rows = self._search(_FakeHTTP())
        first = rows[0]
        # the Funding Agency is the counterparty
        self.assertEqual(first["company"], "HHS")
        # the detail's own description replaces the thin listing teaser
        self.assertIn("America's Seed Fund", first["description"])
        quest = first["quest"]
        self.assertEqual(
            quest["official_solicitation"],
            "https://simpler.grants.gov/opportunity/d1ba49e5-3684-4420-849a-ab2330ec493e",
        )
        self.assertIn("simpler.grants.gov", first["description"])
        self.assertEqual(quest["topic_number"], "PA-27-100")
        self.assertEqual(quest["solicitation_number"], "PA-27-100")
        self.assertEqual(
            quest["due_dates"],
            "September 5, 2026; January 5, 2027; April 5, 2027",
        )
        # the detail schedule's close date wins over the listing's
        self.assertEqual(quest["apply_by"], "2027-04-06")
        # the ROW url stays anchored at the sbir.gov topic page
        self.assertTrue(first["url"].startswith("https://www.sbir.gov/topics/"))

    def test_dod_agency_lines_join_as_counterparty(self) -> None:
        # verbatim from the live topic 12799 detail (fetched 2026-07-12):
        # DOD topics state department then branch as separate lines
        info = self.mod._parse_detail(
            """<div>
  <h3>
   Funding Agency
  </h3>
  <p class="margin-bottom-0">
   DOW
  </p>
  <p class="margin-bottom-0">
   MDA
  </p>
 </div>"""
        )
        self.assertEqual(info["agency"], "DOW / MDA")

    def test_past_deadline_rows_drop(self) -> None:
        rows = self._search(_FakeHTTP(detail=None), now=NOW_LATE)
        self.assertEqual(rows, [])

    def test_no_stated_amount_means_no_salary_keys(self) -> None:
        # the real detail page states no award figure
        for row in self._search(_FakeHTTP()):
            self.assertNotIn("salary_min", row)
            self.assertNotIn("salary_max", row)
            self.assertNotIn("salary_source", row)

    def test_stated_ceiling_maps_to_salary_max_only(self) -> None:
        fields = self.mod._parse_award_ceiling(
            "Phase I awards normally may not exceed six months, with budgets "
            "negotiated up to $306,872 total costs per year."
        )
        self.assertEqual(fields, {"salary_max": 306872.0, "salary_source": "reported"})
        # a dollar figure without a stated ceiling stays off the row
        self.assertEqual(
            self.mod._parse_award_ceiling("The market exceeds $2,000,000 annually."), {}
        )

    def test_pagination_stops_when_a_page_repeats(self) -> None:
        # page 1 repeats page 0's topics; the sweep must notice and stop
        http = _FakeHTTP(pages={0: LISTING, 1: LISTING}, detail=None)
        rows = self._search(http)
        self.assertEqual(len(rows), 3)
        self.assertEqual(http.listing_calls, [0, 1])

    def test_max_results_caps_rows_and_detail_fetches(self) -> None:
        http = _FakeHTTP()
        rows = self._search(http, max_results=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(http.detail_calls), 2)
        # the cap also stops the pager: no page 1 request
        self.assertEqual(http.listing_calls, [0])

    def test_bad_html_returns_empty(self) -> None:
        http = _FakeHTTP(pages={0: "<html><body><p>maintenance</p></body></html>"})
        self.assertEqual(self._search(http), [])
        self.assertEqual(http.detail_calls, [])

    def test_detail_failure_keeps_listing_row(self) -> None:
        rows = self._search(_FakeHTTP(detail=None))
        self.assertEqual(len(rows), 3)
        self.assertNotIn("official_solicitation", rows[0]["quest"])


class SbirRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        from job_finder.tools.scrapers import sbir  # noqa: F401  (registers)
        from job_finder.tools.scrapers._registry import (
            default_scraper_names,
            get_registry,
        )
        meta = get_registry()["sbir"]
        self.assertEqual(meta.display_name, "SBIR.gov")
        self.assertEqual(meta.vertical, "pitch")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("sbir.gov",))
        self.assertFalse(meta.enabled_by_default)
        # quest source: never part of the default career sweep
        self.assertNotIn("sbir", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
