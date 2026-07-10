"""Contract tests for the r/PKMNTCGDeals drop scraper (flip kind).

Fixture is a trimmed REAL response from
https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=PKMNTCGDeals
(captured live 2026-07-09, HTTP 200): two ACTIVE drops, one unflaired
ebay-link resale spam post, one NEWS post. Pins: the mod-applied ACTIVE
flair is the gate, non-thread URLs never pass, and this source NEVER
emits pay (a "$" in a drop post is a retail price, not a payout).
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

FIXTURE = ROOT / "tests" / "fixtures" / "reddit_pkmn_posts.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class RedditPkmnTcgDealsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import reddit_pkmntcgdeals as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_reddit_pkmntcgdeals(**kw)

    def test_active_flair_is_the_gate(self) -> None:
        rows = self._search(_load_fixture())
        # 4 fixture posts: the unflaired ebay spam and the NEWS post drop
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["vertical"], "flip")
            self.assertTrue(row["url"].startswith("https://www.reddit.com/r/PKMNTCGDeals"))

    def test_never_emits_pay(self) -> None:
        for row in self._search(_load_fixture()):
            self.assertNotIn("salary_min", row)
            self.assertNotIn("salary_max", row)

    def test_rows_carry_exact_post_dates(self) -> None:
        for row in self._search(_load_fixture()):
            self.assertIn("date_posted", row)

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, {"data": None}, "x", 42):
            self.assertEqual(self._search(bad), [])


if __name__ == "__main__":
    unittest.main()
