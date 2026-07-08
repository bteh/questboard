"""Contract tests for the r/forhire photo/video gig scraper (lens vertical).

Fixture is a trimmed REAL response from
https://arctic-shift.photon-reddit.com/api/posts/search?subreddit=forhire
(captured live 2026-07-08, HTTP 200, 100 posts per page; 5 representative
posts kept, bodies verbatim). Live-verified quirks pinned here: the fields
param rejects ``permalink`` so ``url`` is the thread deep link, live flairs
are "Hiring"/"For Hire" without brackets, and automod leaves "[removed]"
selftext snapshots that must never leak into descriptions. Also pins the
pay contract: structured salary only for time rates and plain ranges,
per-piece rates stay in quest.pay_note, and the stated string is kept
verbatim. No live HTTP inside tests.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "reddit_forhire_posts.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class RedditForhireParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import reddit_forhire as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_reddit_forhire(**kw)

    def test_parses_fixture_posts(self) -> None:
        rows = self._search(_load_fixture())
        # 5 fixture posts: a For Hire flair and a non-photo/video gig drop.
        self.assertEqual(len(rows), 3)
        editors = rows[0]
        self.assertEqual(
            editors["title"],
            "[HIRING] Looking for Skilled Video Editors ($1000-$4000+)",
        )
        self.assertEqual(editors["company"], "u/Mediocre-Fishing9023")
        self.assertEqual(editors["source"], "reddit-forhire")
        self.assertEqual(editors["vertical"], "lens")
        self.assertEqual(
            editors["url"],
            "https://www.reddit.com/r/forhire/comments/1uqfovo/"
            "hiring_looking_for_skilled_video_editors_10004000/",
        )

    def test_for_hire_flair_is_excluded(self) -> None:
        rows = self._search(_load_fixture())
        self.assertFalse(any("coding/tech" in r["title"] for r in rows))

    def test_non_photo_video_gig_is_excluded(self) -> None:
        rows = self._search(_load_fixture())
        self.assertFalse(any("Singer" in r["title"] for r in rows))

    def test_title_hiring_tag_matches_without_flair(self) -> None:
        payload = copy.deepcopy(_load_fixture())
        editors = payload["data"][2]
        self.assertIn("[HIRING]", editors["title"])
        editors["link_flair_text"] = None
        rows = self._search({"data": [editors]})
        self.assertEqual(len(rows), 1)

    def test_keyword_gate_is_title_only(self) -> None:
        # A hiring post whose body says "video" but whose title does not is
        # noise (video calls, video games), so the gate keys on the title.
        payload = copy.deepcopy(_load_fixture())
        post = payload["data"][2]
        post["title"] = "[Hiring] Assistant needed"
        post["selftext"] = "You will join a video call with our team."
        rows = self._search({"data": [post]})
        self.assertEqual(rows, [])

    def test_date_posted_exact_from_created_utc(self) -> None:
        rows = self._search(_load_fixture())
        self.assertEqual(rows[0]["date_posted"], "2026-07-08T02:21:18+00:00")
        self.assertEqual(rows[1]["date_posted"], "2026-07-07T06:28:28+00:00")

    def test_missing_created_utc_omits_date_posted(self) -> None:
        payload = copy.deepcopy(_load_fixture())
        post = payload["data"][2]
        post["created_utc"] = None
        rows = self._search({"data": [post]})
        self.assertNotIn("date_posted", rows[0])

    def test_removed_body_never_leaks_into_description(self) -> None:
        rows = self._search(_load_fixture())
        editors = rows[0]
        self.assertEqual(editors["description"], "")
        for row in rows:
            self.assertNotIn("[removed]", row["description"])

    def test_live_body_becomes_description(self) -> None:
        rows = self._search(_load_fixture())
        coach = next(r for r in rows if "health/fitness coach" in r["title"])
        self.assertIn("telehealth wellness brand", coach["description"])

    def test_remote_in_title_sets_location(self) -> None:
        rows = self._search(_load_fixture())
        coach = next(r for r in rows if "health/fitness coach" in r["title"])
        self.assertEqual(coach["location"], "Remote")
        editors = rows[0]
        self.assertEqual(editors["location"], "")

    def test_stated_range_becomes_structured_salary(self) -> None:
        rows = self._search(_load_fixture())
        editors = rows[0]
        self.assertEqual(editors["salary_min"], 1000.0)
        self.assertEqual(editors["salary_max"], 4000.0)
        self.assertEqual(editors["salary_source"], "reported")
        self.assertNotIn("salary_period", editors)  # post states no period
        self.assertEqual(editors["quest"]["pay_note"], "$1000-$4000+")

    def test_stated_hourly_rate_carries_period(self) -> None:
        rows = self._search(_load_fixture())
        shortform = next(r for r in rows if "Short form" in r["title"])
        self.assertEqual(shortform["salary_min"], 15.0)
        self.assertEqual(shortform["salary_max"], 15.0)
        self.assertEqual(shortform["salary_period"], "hourly")
        self.assertEqual(shortform["salary_source"], "reported")
        self.assertEqual(shortform["quest"]["pay_note"], "~$15/hr")

    def test_per_piece_rate_stays_note_only(self) -> None:
        # "$200-250/video" is a per-piece rate; the piece count is unknown,
        # so structured salary keys would mislead.
        rows = self._search(_load_fixture())
        coach = next(r for r in rows if "health/fitness coach" in r["title"])
        for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
            self.assertNotIn(key, coach)
        self.assertEqual(coach["quest"]["pay_note"], "~$200-250/video")

    def test_no_stated_figure_means_no_salary_and_no_pay_note(self) -> None:
        payload = copy.deepcopy(_load_fixture())
        post = payload["data"][2]
        post["title"] = "[HIRING] Video editor for a weekly podcast"
        rows = self._search({"data": [post]})
        row = rows[0]
        for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
            self.assertNotIn(key, row)
        self.assertNotIn("quest", row)

    def test_non_thread_url_is_skipped(self) -> None:
        payload = copy.deepcopy(_load_fixture())
        post = payload["data"][2]
        post["url"] = "https://imgur.com/a/portfolio"
        rows = self._search({"data": [post]})
        self.assertEqual(rows, [])

    def test_deleted_author_falls_back_to_subreddit(self) -> None:
        payload = copy.deepcopy(_load_fixture())
        post = payload["data"][2]
        post["author"] = "[deleted]"
        rows = self._search({"data": [post]})
        self.assertEqual(rows[0]["company"], "r/forhire")

    def test_max_results_caps_output(self) -> None:
        rows = self._search(_load_fixture(), max_results=1)
        self.assertEqual(len(rows), 1)

    def test_duplicate_urls_deduped(self) -> None:
        payload = _load_fixture()
        payload["data"] = payload["data"] + payload["data"]
        rows = self._search(payload)
        urls = [r["url"] for r in rows]
        self.assertEqual(len(urls), len(set(urls)))

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, {"data": None}, {"data": "nope"}, [], "x", 42):
            self.assertEqual(self._search(bad), [])
        self.assertEqual(self._search({"data": ["nope", 3]}), [])


class RedditForhirePayExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import reddit_forhire as mod
        self.extract = mod._extract_pay

    def test_dollar_amount_with_letter_suffix_is_not_pay(self) -> None:
        note, fields = self.extract("Our channel has $1M views potential")
        self.assertIsNone(note)
        self.assertEqual(fields, {})

    def test_k_suffix_range(self) -> None:
        note, fields = self.extract("[Hiring] Editor, $1k-$2k per month budget")
        self.assertEqual(fields["salary_min"], 1000.0)
        self.assertEqual(fields["salary_max"], 2000.0)
        self.assertEqual(fields["salary_period"], "monthly")
        self.assertEqual(note, "$1k-$2k per month")

    def test_bare_figure_is_note_only(self) -> None:
        note, fields = self.extract("budget is $5000 and can go higher")
        self.assertEqual(note, "$5000")
        self.assertEqual(fields, {})

    def test_title_wins_over_body(self) -> None:
        note, _ = self.extract("$40/hr", "$10/hr in the body")
        self.assertEqual(note, "$40/hr")


class RedditForhireRegistryTest(unittest.TestCase):
    def test_registered_as_lens_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.reddit_forhire  # noqa: F401
        reg = get_registry()
        self.assertIn("reddit-forhire", reg)
        meta = reg["reddit-forhire"]
        self.assertEqual(meta.vertical, "lens")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_never_in_default_career_sweep(self) -> None:
        import job_finder.tools.scrapers  # noqa: F401  (triggers registration)
        from job_finder.tools.scrapers._registry import default_scraper_names
        self.assertNotIn("reddit-forhire", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
