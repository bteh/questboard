"""Contract tests for the Doctor of Credit bonus scraper (house kind).

Fixture is a trimmed REAL response from
https://www.doctorofcredit.com/wp-json/wp/v2/posts?categories=142,215
(captured live 2026-07-09, HTTP 200) plus one synthesized "Up To" title.
Live-verified quirks pinned here: dead offers get retitled "[Expired] ..."
while still sitting in the current category, roundup posts carry no "$"
in the title, a leading bracket names state availability, and the "Offer
at a glance" block carries the source's own hard-pull and ChexSystems
facts. No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "doctorofcredit_posts.json"


def _load_fixture() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class DoctorOfCreditTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import doctorofcredit as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_doctorofcredit(**kw)

    def test_parses_live_bonuses_only(self) -> None:
        rows = self._search(_load_fixture())
        titles = [r["title"] for r in rows]
        # 6 fixture posts: the [Expired] one and the no-$ roundup drop
        self.assertEqual(len(rows), 4)
        self.assertFalse(any("[Expired" in t for t in titles))
        self.assertFalse(any("A List Of" in t for t in titles))
        for row in rows:
            self.assertEqual(row["vertical"], "house")
            self.assertTrue(row["url"].startswith("https://www.doctorofcredit.com/"))

    def test_bracket_prefix_becomes_location_and_leaves_the_title(self) -> None:
        rows = self._search(_load_fixture())
        bar_harbor = next(r for r in rows if "Bar Harbor" in r["title"])
        self.assertEqual(bar_harbor["location"], "ME, VT & NH")
        self.assertFalse(bar_harbor["title"].startswith("["))

    def test_stated_amount_maps_to_exact_pay(self) -> None:
        rows = self._search(_load_fixture())
        mt = next(r for r in rows if r["title"].startswith("M&T Bank"))
        self.assertEqual(mt["salary_min"], 400.0)
        self.assertEqual(mt["salary_max"], 400.0)
        self.assertEqual(mt["salary_source"], "reported")

    def test_deposit_and_drip_amounts_never_count_as_the_bonus(self) -> None:
        """Live-audit regression (2026-07-10): 'Deposit $5,000+ & Earn $250
        Bonus' rendered a $250-5000 reward; the deposit is the COST."""
        payload = _load_fixture()
        trade = dict(payload[0])
        trade["id"] = 999300
        trade["title"] = {"rendered": "TradeStation: Deposit $5,000+ &#038; Earn $250 Bonus"}
        trade["link"] = "https://www.doctorofcredit.com/tradestation-deposit-probe"
        drip = dict(payload[0])
        drip["id"] = 999301
        drip["title"] = {"rendered": "Valley National Bank $240 Checking Bonus ($20 Per Month)"}
        drip["link"] = "https://www.doctorofcredit.com/valley-drip-probe"
        rows = self._search(payload + [trade, drip])

        ts = next(r for r in rows if "TradeStation" in r["title"])
        assert ts["salary_min"] == 250.0 and ts["salary_max"] == 250.0
        vy = next(r for r in rows if "Valley National" in r["title"])
        assert vy["salary_min"] == 240.0 and vy["salary_max"] == 240.0

    def test_parenthesized_mechanics_never_count_as_the_bonus(self) -> None:
        """DoC puts requirements in parens: deposit terms, asset minimums."""
        payload = _load_fixture()
        for i, (title, want) in enumerate((
            ("316 Financial $250 Savings Bonus ($5,000 For 150 Days)", 250.0),
            ("TradeStation $50-$5,000 Brokerage Bonus ($5,000-$5,000,000 In Qualifying Assets Required)", 5000.0),
        )):
            post = dict(payload[0])
            post["id"] = 999400 + i
            post["title"] = {"rendered": title}
            post["link"] = f"https://www.doctorofcredit.com/paren-probe-{i}"
            payload.append(post)
        rows = self._search(payload)

        fin = next(r for r in rows if "316 Financial" in r["title"])
        assert fin["salary_min"] == 250.0 and fin["salary_max"] == 250.0
        ts = next(r for r in rows if "Brokerage" in r["title"])
        assert ts["salary_min"] == 50.0 and ts["salary_max"] == 5000.0

    def test_up_to_promises_a_ceiling_never_a_floor(self) -> None:
        rows = self._search(_load_fixture())
        citi = next(r for r in rows if "Citibank" in r["title"])
        self.assertEqual(citi["salary_max"], 2000.0)
        self.assertNotIn("salary_min", citi)

    def test_glance_block_feeds_description_and_quest(self) -> None:
        rows = self._search(_load_fixture())
        with_glance = [r for r in rows if r.get("quest")]
        self.assertTrue(with_glance, "at least one fixture post carries the glance block")
        row = with_glance[0]
        self.assertIn("pull", {**row["quest"], "pull": row["quest"].get("pull", "")})
        self.assertTrue(row["description"])

    def test_no_posted_date_claim_ever(self) -> None:
        # DoC re-runs years-old posts for live offers; a publish date would
        # render "posted 30 months ago" on a bonus that is current today
        for row in self._search(_load_fixture()):
            self.assertNotIn("date_posted", row)

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, "x", 42, {"data": []}):
            self.assertEqual(self._search(bad), [])


if __name__ == "__main__":
    unittest.main()
