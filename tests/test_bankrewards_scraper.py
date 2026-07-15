"""Contract tests for the bankrewards.io bonus scraper (house kind).

Fixture is a trimmed REAL response from POST https://bankrewards.io/api/offers
(captured live 2026-07-15, plain Mozilla/5.0 UA, HTTP 200). Eight real
records, one per filter case: three keepers (nationwide $550, nationwide
business bank, multi-state business bank) and five drops that each exercise a
distinct filter (single-state geo, older-than-90-days, sub-$150, a referral
offer_link, a credit card). The one edit to real data: the referral row
(Together Credit Union, a member-referral link) had its ``updated_at`` bumped
recent so the referral strip is the SOLE reason it drops, not recency.

The recency window is pinned by patching ``_now`` to a fixed date so the test
stays stable as the fixture ages. No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "bankrewards_offers.json"

# Fixed "now" so the 90-day recency window is deterministic against the
# fixture's real timestamps (June 2026 rows are recent; Jan/Feb rows are old).
_NOW = datetime(2026, 7, 15)


def _load_fixture() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class BankRewardsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import bankrewards as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_offers", return_value=payload), \
             patch.object(self.mod, "_now", return_value=_NOW):
            return self.mod.search_bankrewards(**kw)

    def test_filters_leave_only_the_three_valid_keepers(self) -> None:
        rows = self._search(_load_fixture())
        companies = {r["company"] for r in rows}
        # kept: nationwide $550, nationwide business bank, multi-state biz bank
        self.assertEqual(len(rows), 3)
        self.assertIn("Four Leaf Federal Credit Union", companies)
        self.assertIn("Rho", companies)
        self.assertIn("Popular Bank", companies)
        # every kept row is a house-kind cash bonus at/over the floor
        for row in rows:
            self.assertEqual(row["vertical"], "house")
            self.assertEqual(row["source"], "bankrewards")
            self.assertGreaterEqual(row["salary_min"], 150)
            self.assertEqual(row["salary_min"], row["salary_max"])
            self.assertEqual(row["salary_source"], "reported")

    def test_drops_single_state_offer(self) -> None:
        # People Driven CU is $500 but only ["MI"]; geo filter kills it.
        rows = self._search(_load_fixture())
        self.assertNotIn(
            "People Driven Credit Union Business Checking",
            {r["company"] for r in rows},
        )

    def test_drops_offer_older_than_the_recency_window(self) -> None:
        # Bank of America Business is nationwide $750 but updated 2026-02-12,
        # more than 90 days before the pinned now; presumed dead.
        rows = self._search(_load_fixture())
        self.assertNotIn("Bank of America Business", {r["company"] for r in rows})

    def test_drops_offer_below_the_bonus_floor(self) -> None:
        # Valley National Bank is nationwide but only $100.
        rows = self._search(_load_fixture())
        self.assertNotIn("Valley National Bank", {r["company"] for r in rows})

    def test_strips_referral_offer_links(self) -> None:
        # Together Credit Union otherwise qualifies (bank, 3 states, $150,
        # recent) but offer_link is a member-referral; it must not publish,
        # and no surviving row may carry a referral link.
        rows = self._search(_load_fixture())
        self.assertNotIn("Together Credit Union", {r["company"] for r in rows})
        for row in rows:
            self.assertFalse(
                self.mod._is_referral_link(row["url"]),
                f"referral link leaked: {row['url']}",
            )

    def test_credit_cards_do_not_belong_to_this_lane(self) -> None:
        # Cards go to card_onramps; bankrewards keeps bank/business_bank only.
        rows = self._search(_load_fixture())
        self.assertNotIn("Target", {r["company"] for r in rows})

    def test_nationwide_row_renders_amount_requirement_geo_and_listed(self) -> None:
        rows = self._search(_load_fixture())
        four_leaf = next(r for r in rows if r["company"] == "Four Leaf Federal Credit Union")
        self.assertEqual(four_leaf["salary_min"], 550.0)
        desc = four_leaf["description"]
        self.assertIn("$550", desc)
        self.assertIn("after a direct deposit of $500", desc)
        self.assertIn("nationwide", desc)
        self.assertIn("as listed 2026-06", desc)
        # nationwide is do-anywhere: no state in the location field
        self.assertEqual(four_leaf["location"], "")
        # the catch is the requirement and geo as stated
        self.assertIn("a direct deposit of $500", four_leaf["quest"]["catch"])
        self.assertIn("nationwide", four_leaf["quest"]["catch"])

    def test_multi_state_row_keeps_the_state_list(self) -> None:
        rows = self._search(_load_fixture())
        popular = next(r for r in rows if r["company"] == "Popular Bank")
        self.assertEqual(popular["location"], "FL, NJ, NY")
        self.assertIn("FL, NJ, NY only", popular["description"])
        self.assertEqual(popular["salary_min"], 400.0)

    def test_referral_detector_flags_referral_but_not_issuer_direct(self) -> None:
        referral = [
            "https://bilt.page/r/IROM-C5VR",
            "https://citbank.sjv.io/c/5324098/2720745/30164",
            "https://api.fintelconnect.com/t/l/6939c862aacae8082465a05c",
            "https://www.togethercu.org/member-referral",
            "https://www.americanexpress.com/en-us/referral/personal/blue-cash-everyday-credit-card?ref=MITCHP8Nyk",
        ]
        direct = [
            "https://www.fourleaffcu.com/queens-open-an-account/",
            "https://banking.citi.com/cbol/OM/checking/choice/featured-offers/default.htm",
            "https://www.rho.co/lp/affiliate-banking",
            "https://www.popularbank.com/business/deposits/",
        ]
        for url in referral:
            self.assertTrue(self.mod._is_referral_link(url), url)
        for url in direct:
            self.assertFalse(self.mod._is_referral_link(url), url)

    def test_no_em_dashes_anywhere(self) -> None:
        rows = self._search(_load_fixture())
        for row in rows:
            values = list(row.values()) + list(row.get("quest", {}).values())
            for value in values:
                if isinstance(value, str):
                    self.assertNotIn("\u2014", value, row["company"])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["bankrewards"]
        self.assertEqual(meta.vertical, "house")
        self.assertTrue(meta.full_snapshot)
        self.assertFalse(meta.enabled_by_default)
        rows = self._search(_load_fixture())
        valid, rejected = validate_rows(rows, meta, now=_NOW)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), len(rows))

    def test_bad_payload_returns_empty(self) -> None:
        for bad in ([], [None, "x", 42]):
            self.assertEqual(self._search(bad), [])


if __name__ == "__main__":
    unittest.main()
