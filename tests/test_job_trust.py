"""Tests for the trust/freshness signals (ghost-job defense).

Pins the source-tier classification and the true-age freshness buckets,
including the load-bearing rule that an unverifiable date never reads as
"fresh" (that's the false-freshness a repost exploits).
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.job_trust import (  # noqa: E402
    classify_freshness,
    is_direct_source,
    is_stale,
    posting_age_days,
)

NOW = datetime(2026, 7, 6, tzinfo=timezone.utc)


def _days_ago(n: int) -> str:
    return (NOW - timedelta(days=n)).strftime("%Y-%m-%d")


class DirectSourceTest(unittest.TestCase):
    def test_ats_sources_are_direct(self) -> None:
        for s in ("greenhouse", "lever", "ashby", "workable", "workday",
                  "consider", "getro", "yc_workatastartup"):
            self.assertTrue(is_direct_source(s), s)

    def test_case_insensitive(self) -> None:
        self.assertTrue(is_direct_source("Greenhouse"))
        self.assertTrue(is_direct_source("  WORKABLE "))

    def test_aggregators_and_engines_are_not_direct(self) -> None:
        for s in ("linkedin", "indeed", "glassdoor", "zip_recruiter", "google",
                  "remoteok", "remotive", "weworkremotely", "himalayas",
                  "hackernews", ""):
            self.assertFalse(is_direct_source(s), s)

    def test_none_is_not_direct(self) -> None:
        self.assertFalse(is_direct_source(None))


class PostingAgeTest(unittest.TestCase):
    def test_recent_date(self) -> None:
        self.assertEqual(posting_age_days(_days_ago(3), now=NOW), 3)

    def test_future_date_clamps_to_zero(self) -> None:
        future = (NOW + timedelta(days=5)).strftime("%Y-%m-%d")
        self.assertEqual(posting_age_days(future, now=NOW), 0)

    def test_unparseable_is_none(self) -> None:
        self.assertIsNone(posting_age_days("not a date", now=NOW))
        self.assertIsNone(posting_age_days(None, now=NOW))
        self.assertIsNone(posting_age_days("", now=NOW))

    def test_iso_with_time(self) -> None:
        iso = (NOW - timedelta(days=10)).isoformat()
        self.assertEqual(posting_age_days(iso, now=NOW), 10)


class FreshnessTest(unittest.TestCase):
    def test_buckets(self) -> None:
        self.assertEqual(classify_freshness(_days_ago(2), "exact", now=NOW), "fresh")
        self.assertEqual(classify_freshness(_days_ago(7), "exact", now=NOW), "fresh")
        self.assertEqual(classify_freshness(_days_ago(20), "exact", now=NOW), "recent")
        self.assertEqual(classify_freshness(_days_ago(30), "exact", now=NOW), "recent")
        self.assertEqual(classify_freshness(_days_ago(45), "exact", now=NOW), "aging")
        self.assertEqual(classify_freshness(_days_ago(60), "exact", now=NOW), "aging")
        self.assertEqual(classify_freshness(_days_ago(90), "exact", now=NOW), "stale")

    def test_missing_confidence_is_unknown_not_fresh(self) -> None:
        # Even a today-stamped date is "unknown" when the source flagged it a guess.
        self.assertEqual(classify_freshness(_days_ago(1), "missing", now=NOW), "unknown")

    def test_unparseable_date_is_unknown(self) -> None:
        self.assertEqual(classify_freshness("garbage", "exact", now=NOW), "unknown")
        self.assertEqual(classify_freshness(None, None, now=NOW), "unknown")

    def test_fuzzy_confidence_still_classifies(self) -> None:
        self.assertEqual(classify_freshness(_days_ago(3), "fuzzy", now=NOW), "fresh")

    def test_is_stale_only_when_proven(self) -> None:
        self.assertTrue(is_stale(_days_ago(120), "exact", now=NOW))
        self.assertFalse(is_stale(_days_ago(3), "exact", now=NOW))
        # unknown date is NOT stale (we don't punish what we can't prove)
        self.assertFalse(is_stale(None, "missing", now=NOW))


if __name__ == "__main__":
    unittest.main()
