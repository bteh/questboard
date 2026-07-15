"""Contract tests for the curated credit-card welcome-offer on-ramps.

The data IS the content (no network at runtime), so these tests pin the
honesty and Reg Z contract on the rows themselves: bonus and spend only in
the issuer's words, NEVER an APR or fee number, links to the issuer's own
domain, a bring and a catch on every row, and no em dashes.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# Rate/fee wording that Reg Z compliance forbids us from stating ourselves.
_FEE_WORDS_RE = re.compile(r"\bAPR\b|annual fee|interest rate|\bfee\b", re.IGNORECASE)
_ISSUER_DOMAINS = (
    "chase.com",
    "capitalone.com",
    "wellsfargo.com",
    "discover.com",
    "bankofamerica.com",
)


def _host_ok(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in _ISSUER_DOMAINS)


class CardOnrampsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import card_onramps as mod
        self.mod = mod
        self.rows = mod.search_card_onramps()

    def test_returns_a_small_hand_set(self) -> None:
        self.assertGreaterEqual(len(self.rows), 5)
        self.assertLessEqual(len(self.rows), 8)

    def test_every_row_is_actionable(self) -> None:
        for row in self.rows:
            self.assertTrue(row["title"].strip(), row)
            self.assertTrue(row["company"].strip(), row)
            self.assertTrue(row["url"].startswith("https://"), row["url"])
            self.assertEqual(row["vertical"], "house")
            self.assertEqual(row["source"], "card_onramps")

    def test_urls_point_at_the_issuer_domain(self) -> None:
        for row in self.rows:
            self.assertTrue(_host_ok(row["url"]), row["url"])

    def test_never_quotes_a_rate_or_fee_number(self) -> None:
        for row in self.rows:
            for value in list(row.values()) + list(row["quest"].values()):
                if not isinstance(value, str):
                    continue
                # a percent sign would be an APR/rate we must not state
                self.assertNotIn("%", value, f"{row['company']}: {value}")
                self.assertIsNone(
                    _FEE_WORDS_RE.search(value),
                    f"{row['company']} states a rate/fee word: {value}",
                )

    def test_description_states_a_bonus_and_defers_terms(self) -> None:
        for row in self.rows:
            desc = row["description"]
            # a stated bonus: a dollar amount, a point/mile count, or a match
            self.assertTrue(
                re.search(r"\$\d|\d[\d,]*\s+(?:bonus\s+)?(?:points|miles)|match", desc),
                f"{row['company']}: {desc}",
            )
            self.assertIn("as listed", desc)
            self.assertIn("terms on", desc)

    def test_pay_is_never_invented(self) -> None:
        for row in self.rows:
            self.assertIsNone(row["salary_min"], row["company"])
            self.assertIsNone(row["salary_max"], row["company"])
            self.assertEqual(row["date_posted"], "", row["company"])
            self.assertTrue(row["is_rolling"])
            self.assertIsInstance(row["first_quest_ok"], bool)

    def test_every_row_states_its_bring_and_catch(self) -> None:
        for row in self.rows:
            quest = row["quest"]
            self.assertTrue(quest["bring"].strip(), row["company"])
            catch = quest["catch"]
            self.assertIn("hard credit pull", catch, row["company"])
            self.assertIn("never carry a balance", catch, row["company"])

    def test_no_em_dashes_anywhere(self) -> None:
        for row in self.rows:
            for value in list(row.values()) + list(row["quest"].values()):
                if isinstance(value, str):
                    self.assertNotIn("\u2014", value, row["company"])

    def test_max_results_respected(self) -> None:
        self.assertEqual(len(self.mod.search_card_onramps(max_results=3)), 3)
        self.assertEqual(self.mod.search_card_onramps(max_results=0), [])

    def test_rows_pass_the_row_contract(self) -> None:
        from job_finder.row_contract import validate_rows
        from job_finder.tools.scrapers._registry import get_registry

        meta = get_registry()["card_onramps"]
        self.assertEqual(meta.vertical, "house")
        self.assertTrue(meta.full_snapshot)
        self.assertFalse(meta.enabled_by_default)
        valid, rejected = validate_rows(self.rows, meta)
        self.assertEqual(rejected, [])
        self.assertEqual(len(valid), len(self.rows))


if __name__ == "__main__":
    unittest.main()
