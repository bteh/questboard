"""Ashby's null fields must not cost a whole company board.

Ashby's posting API declares `workplaceType` and `location` as strings, and
sends JSON null for them on a large share of real postings. `dict.get(k, "")`
returns the default only when the key is ABSENT; a key present with value null
returns None, so `.lower()` raised AttributeError on those rows.

That exception escaped `_fetch_company_jobs` and was caught in `search_ashby`'s
`as_completed` loop, which logs at DEBUG and moves on. The whole company's
postings were discarded with nothing visible to say so, including the ones
already collected before the bad row.

Measured 2026-07-27 against the live cache: 25 of a 60-slug sample raised it,
so roughly 40% of Ashby companies were contributing nothing to the board while
the source reported healthy. Found by probing every cached slug and noticing
the "unreachable" count was 109/247 on Ashby and 0-1 on the other three hosts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


def _job(**overrides) -> dict:
    """An Ashby posting shaped like the real live payload."""
    base = {
        "title": "Senior Data Engineer",
        "jobUrl": "https://jobs.ashbyhq.com/acme/abc123",
        "descriptionPlain": "We need a data engineer with dbt.",
        "location": "San Francisco, CA",
        "isRemote": False,
        "workplaceType": "Onsite",
        "publishedAt": "2026-06-01T00:00:00Z",
        "employmentType": "FullTime",
    }
    base.update(overrides)
    return base


class AshbyNullFieldTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import ashby as mod
        self.mod = mod

    def _fetch(self, jobs):
        with patch.object(self.mod, "_get_json", return_value={"jobs": jobs}):
            return self.mod._fetch_company_jobs("acme", ["data engineer"])

    def test_a_null_workplace_type_does_not_lose_the_posting(self):
        """The live failure: 'NoneType' object has no attribute 'lower'."""
        rows = self._fetch([_job(workplaceType=None)])
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_remote"])

    def test_a_null_location_does_not_lose_the_posting(self):
        rows = self._fetch([_job(location=None)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["location"], "")

    def test_one_bad_posting_does_not_take_the_rest_of_the_board(self):
        """The expensive part of the bug. The exception escaped mid-loop, so a
        company's good postings died alongside the null one."""
        rows = self._fetch([
            _job(title="Senior Data Engineer"),
            _job(title="Staff Data Engineer", workplaceType=None),
            _job(title="Lead Data Engineer"),
        ])
        self.assertEqual(len(rows), 3)

    def test_a_stated_remote_workplace_still_reads_as_remote(self):
        """Fixing the crash must not cost the signal. Ashby's flag is
        authoritative downstream, so this is the behavior worth keeping."""
        rows = self._fetch([_job(workplaceType="Remote", isRemote=False)])
        self.assertTrue(rows[0]["is_remote"])
        self.assertTrue(rows[0]["remote_flag_reported"])

    def test_the_is_remote_flag_still_wins_on_its_own(self):
        rows = self._fetch([_job(isRemote=True, workplaceType=None)])
        self.assertTrue(rows[0]["is_remote"])


class AshbyWorkplaceTypeTest(unittest.TestCase):
    """`workplaceType` is the precise field; `isRemote` is not.

    Airwallex's "Manager, Data Engineering" is served by Ashby as:
        location:      "US - San Francisco"
        isRemote:      true
        workplaceType: "Hybrid"
    and Airwallex's own page states Location Type: Hybrid. Reading isRemote
    first put a hybrid San Francisco role on a Los Angeles + remote board.

    Measured 2026-07-27 across 80 cached boards: 995 of 4954 postings carry
    isRemote=true with workplaceType=hybrid, and isRemote is never true
    alongside onsite. Ashby's isRemote means "not strictly onsite", so it
    cannot answer "is this remote" on its own.

    This compounds: the scraper stamps remote_flag_reported, which
    company_classifier treats as definitive, skipping both its description
    scan for hybrid wording and its own rule that a board-reported remote flag
    on a job with a physical address deserves skepticism.
    """

    def setUp(self) -> None:
        from job_finder.tools.scrapers import ashby as mod
        self.mod = mod

    def _row(self, **overrides):
        with patch.object(self.mod, "_get_json", return_value={"jobs": [_job(**overrides)]}):
            rows = self.mod._fetch_company_jobs("acme", ["data engineer"])
        return rows[0]

    def test_a_hybrid_posting_is_not_remote_even_when_is_remote_is_set(self):
        row = self._row(
            location="US - San Francisco", isRemote=True, workplaceType="Hybrid"
        )
        self.assertFalse(row["is_remote"])

    def test_a_hybrid_posting_does_not_claim_a_definitive_remote_flag(self):
        """Leaving this set tells the classifier to stop asking questions."""
        row = self._row(
            location="US - San Francisco", isRemote=True, workplaceType="Hybrid"
        )
        self.assertFalse(row["remote_flag_reported"])

    def test_a_remote_posting_is_still_remote(self):
        row = self._row(location="Remote", isRemote=True, workplaceType="Remote")
        self.assertTrue(row["is_remote"])
        self.assertTrue(row["remote_flag_reported"])

    def test_an_onsite_posting_is_not_remote(self):
        row = self._row(location="SG - Singapore", isRemote=False, workplaceType="OnSite")
        self.assertFalse(row["is_remote"])

    def test_workplace_type_outranks_is_remote_whichever_way_they_disagree(self):
        self.assertTrue(
            self._row(isRemote=False, workplaceType="Remote")["is_remote"]
        )

    def test_a_missing_workplace_type_falls_back_to_is_remote(self):
        """454 of that same sample state no workplaceType at all."""
        self.assertTrue(self._row(isRemote=True, workplaceType=None)["is_remote"])
        self.assertFalse(self._row(isRemote=False, workplaceType=None)["is_remote"])

    def test_the_workplace_type_match_ignores_case_and_padding(self):
        self.assertTrue(self._row(isRemote=False, workplaceType=" REMOTE ")["is_remote"])
        self.assertFalse(self._row(isRemote=True, workplaceType="hybrid")["is_remote"])


class AshbyBoardSurvivalTest(unittest.TestCase):
    """The user-visible half: the company reaches the board at all."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers import ashby as mod
        self.mod = mod

    def test_a_company_with_null_workplace_types_still_reaches_the_board(self):
        payload = {"jobs": [_job(workplaceType=None)]}
        with patch.object(self.mod, "_get_json", return_value=payload):
            rows = self.mod.search_ashby(roles=["data engineer"], companies=["acme"])
        self.assertEqual(len(rows), 1, "the board was silently dropped")

    def test_a_failing_board_is_logged_loudly_enough_to_notice(self):
        """Ashby logged board failures at DEBUG where Lever, Greenhouse and
        Workable use WARNING. That gap is why a crash on ~40% of boards looked
        like a healthy source for as long as it did.
        """
        with patch.object(self.mod, "_get_json", side_effect=ValueError("boom")):
            with self.assertLogs(self.mod.logger, level="WARNING"):
                self.mod.search_ashby(roles=["data engineer"], companies=["acme"])


if __name__ == "__main__":
    unittest.main()
