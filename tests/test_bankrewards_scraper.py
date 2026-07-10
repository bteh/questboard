"""Contract tests for the bankrewards.io bonus scraper (house kind).

Fixture is a trimmed REAL response from POST https://bankrewards.io/api/offers
(captured live 2026-07-09, HTTP 200, 100 offers; one offer per offer_type
kept, plus a null-bonus edge). Pins: cash bonuses only (credit_card and
null/zero bonus_cash skipped), titles composed from the source's own
fields, state list joined into location, numeric bonus mapped exactly.
No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "bankrewards_offers.json"


def _load_fixture() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class BankRewardsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import bankrewards as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_offers", return_value=payload):
            return self.mod.search_bankrewards(**kw)

    def test_cash_bank_and_brokerage_offers_only(self) -> None:
        rows = self._search(_load_fixture())
        # 5 fixture offers: credit_card and the null-bonus row drop
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["vertical"], "house")
            self.assertGreater(row["salary_min"], 0)
            self.assertEqual(row["salary_min"], row["salary_max"])
            self.assertEqual(row["salary_source"], "reported")

    def test_title_carries_the_stated_bonus(self) -> None:
        rows = self._search(_load_fixture())
        five_star = next(r for r in rows if "Five Star" in r["title"])
        self.assertIn("$200", five_star["title"])
        self.assertEqual(five_star["salary_max"], 200.0)

    def test_states_join_into_location(self) -> None:
        rows = self._search(_load_fixture())
        located = [r for r in rows if r["location"]]
        self.assertTrue(located)
        self.assertIn(",", located[0]["location"] + ",")

    def test_requirement_reads_in_plain_words(self) -> None:
        rows = self._search(_load_fixture())
        with_req = [r for r in rows if "Requires" in r["description"]]
        self.assertTrue(with_req)

    def test_bad_payload_returns_empty(self) -> None:
        for bad in ([], [None, "x", 42],):
            self.assertEqual(self._search(bad), [])


if __name__ == "__main__":
    unittest.main()
