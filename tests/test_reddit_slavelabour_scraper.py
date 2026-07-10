"""Contract tests for the r/slavelabour task scraper (odd kind).

Fixture is a trimmed REAL response from
https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=slavelabour
(captured live 2026-07-09, HTTP 200) plus one synthesized manipulation
task. Pins: [Task] flair is the gate (an [Offer] is someone selling
labor, not a quest), platform-manipulation and gift-card tasks are
excluded by house rules, and pay comes only from the shared stated-pay
extractor. No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "reddit_slavelabour_posts.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class RedditSlavelabourTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import reddit_slavelabour as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_reddit_slavelabour(**kw)

    def test_task_flair_is_the_gate(self) -> None:
        rows = self._search(_load_fixture())
        titles = [r["title"] for r in rows]
        self.assertFalse(any(t.lower().startswith("[offer]") for t in titles))
        for row in rows:
            self.assertEqual(row["vertical"], "odd")
            self.assertTrue(row["url"].startswith("https://www.reddit.com/r/slavelabour"))

    def test_manipulation_tasks_fail_house_rules(self) -> None:
        rows = self._search(_load_fixture())
        self.assertFalse(any("upvote" in r["title"].lower() for r in rows))

    def test_stated_title_pay_lands_in_pay_note(self) -> None:
        rows = self._search(_load_fixture())
        paid = [r for r in rows if r.get("quest", {}).get("pay_note")]
        self.assertTrue(paid, "at least one fixture task states pay in its title")
        self.assertIn("$", paid[0]["quest"]["pay_note"])

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, {"data": None}, "x", 42):
            self.assertEqual(self._search(bad), [])


if __name__ == "__main__":
    unittest.main()
