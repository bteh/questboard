"""rank_by_relevance must break ties deterministically, newest first.

_relevance_score only yields 3/2/1/0 and sorted() is stable, so within a
tier rows kept whatever order the fetch threads happened to finish in. With
all four ATS sources saturating their 500-row cap on 2026-08-16, which rows
died was timing: TRM Labs' newer Ashby posting was truncated while its
older one survived, and Figma's "Manager, Software Engineering - Data
Platform" (curated seed) vanished on some runs. Within a tier, newer
postings must sort first, undated rows last, and the final tie-break must
be a stable row key, never thread-completion order.
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers._utils import rank_by_relevance  # noqa: E402

ROLES = ["data engineer"]


def _row(title: str, company: str, url: str, date_posted) -> dict:
    return {
        "title": title,
        "company": company,
        "url": url,
        "date_posted": date_posted,
    }


class RecencyTieBreakTest(unittest.TestCase):
    def test_newer_same_tier_posting_wins_at_the_cap_boundary_trm_labs(self):
        """The real casualty: TRM Labs' newer Ashby posting was the one the
        cap cut while the older survived."""
        older = _row(
            "Senior Data Engineer", "TRM Labs",
            "https://jobs.ashbyhq.com/trmlabs/old", "2026-04-20T00:00:00Z",
        )
        newer = _row(
            "Staff Data Engineer", "TRM Labs",
            "https://jobs.ashbyhq.com/trmlabs/new", "2026-08-10T00:00:00Z",
        )
        for order in ([older, newer], [newer, older]):
            kept = rank_by_relevance(list(order), ROLES)[:1]
            self.assertEqual(kept[0]["url"], newer["url"])

    def test_undated_rows_sort_after_dated_rows_in_the_same_tier(self):
        undated = _row("Data Engineer", "NoDate Co", "https://x/1", "")
        dated = _row("Data Engineer", "Dated Co", "https://x/2", "2026-01-05")
        for order in ([undated, dated], [dated, undated]):
            ranked = rank_by_relevance(list(order), ROLES)
            self.assertEqual(ranked[0]["company"], "Dated Co")

    def test_relevance_tier_still_outranks_recency_figma(self):
        """Recency is a tie-break only. Figma's tier-2 title must not jump
        above an exact tier-3 match just because it is newer."""
        exact_old = _row(
            "Data Engineer", "Old Exact Co", "https://x/1", "2025-01-01",
        )
        figma_new = _row(
            "Manager, Software Engineering - Data Platform", "Figma",
            "https://x/2", "2026-08-15",
        )
        ranked = rank_by_relevance([figma_new, exact_old], ROLES)
        self.assertEqual(ranked[0]["company"], "Old Exact Co")

    def test_lever_epoch_ms_dates_participate_in_recency(self):
        """Lever emits createdAt as epoch milliseconds, not ISO strings."""
        older = _row("Data Engineer", "Lever Old", "https://x/1", 1746057600000)
        newer = _row("Data Engineer", "Lever New", "https://x/2", 1786320000000)
        for order in ([older, newer], [newer, older]):
            ranked = rank_by_relevance(list(order), ROLES)
            self.assertEqual(ranked[0]["company"], "Lever New")

    def test_shuffled_thread_orders_yield_identical_ranking(self):
        """Two runs of the same scrape differ only in thread completion
        order. The ranked output must be byte-for-byte identical."""
        titles = [
            "Data Engineer", "Senior Data Engineer", "Staff Data Engineer",
            "Manager of Data Engineering", "Data Analyst", "Data Scientist",
        ]
        dates = ["2026-08-10", "2026-06-01", "2026-01-15", "", None]
        rows = [
            _row(titles[i % len(titles)], f"Co {i:02d}",
                 f"https://x/{i}", dates[i % len(dates)])
            for i in range(40)
        ]
        first = list(rows)
        second = list(rows)
        random.Random(0).shuffle(first)
        random.Random(1).shuffle(second)
        self.assertEqual(
            rank_by_relevance(first, ROLES),
            rank_by_relevance(second, ROLES),
        )


if __name__ == "__main__":
    unittest.main()
