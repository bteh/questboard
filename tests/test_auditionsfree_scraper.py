"""Contract tests for the AuditionsFree casting-call scraper.

The fixture is a trimmed real response from
https://www.auditionsfree.com/wp-json/wp/v2/posts (live-probed HTTP 200,
July 2026): three representative posts covering a labeled no-pay theater
call, a paid extras call with the "$100/8hrs" day-rate shorthand, and a
multi-rate Netflix notice with an en-dash age range and an explicit
"experience ... not required" line. These tests pin the WP payload parse,
labeled location/company extraction, pay-only-when-stated, age bounds,
first_quest_ok, pagination/cap, graceful degradation, and registration
under vertical="camera" with enabled_by_default=False.
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

FIXTURE = ROOT / "tests" / "fixtures" / "auditionsfree_posts.json"


def _fixture_posts() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _post(i: int = 0, **overrides) -> dict:
    """A minimal WP post object shaped like the live payload."""
    base = {
        "id": 1000 + i,
        "date": "2026-07-01T00:00:00",
        "date_gmt": "2026-07-01T08:00:00",
        "link": f"https://www.auditionsfree.com/2026/casting-call-{i}/",
        "title": {"rendered": f"Casting Call {i}"},
        "content": {"rendered": "<p>Location: Los Angeles, CA</p>"},
    }
    base.update(overrides)
    return base


class AuditionsFreeFixtureParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import auditionsfree as mod
        self.mod = mod
        with patch.object(mod, "_get_json", return_value=_fixture_posts()):
            self.rows = mod.search_auditionsfree(max_results=50)

    def test_parses_all_posts(self) -> None:
        self.assertEqual(len(self.rows), 3)
        for row in self.rows:
            self.assertEqual(row["source"], "auditionsfree")
            self.assertEqual(row["vertical"], "camera")
            self.assertTrue(row["url"].startswith("https://www.auditionsfree.com/"))
            self.assertTrue(row["title"])
            self.assertNotIn("&#8220;", row["title"])
            self.assertNotIn("<p>", row["description"])

    def test_theater_call_without_stated_pay(self) -> None:
        row = self.rows[0]
        self.assertIn("Awakening", row["title"])
        self.assertEqual(row["location"], "Las Vegas, Nevada")
        self.assertEqual(row["company"], "Wynn Las Vegas")
        self.assertEqual(row["date_posted"], "2026-07-02T00:27:40")
        self.assertNotIn("salary_min", row)
        self.assertNotIn("salary_source", row)
        self.assertNotIn("first_quest_ok", row)

    def test_paid_extras_call_day_rate(self) -> None:
        row = self.rows[1]
        self.assertTrue(row["location"].startswith("Nashville, TN"))
        self.assertEqual(row["salary_min"], 100.0)
        self.assertEqual(row["salary_max"], 100.0)
        self.assertEqual(row["salary_period"], "daily")
        self.assertEqual(row["salary_source"], "reported")
        quest = row["quest"]
        self.assertEqual(quest["age_min"], 21)
        self.assertEqual(quest["age_max"], 65)
        self.assertEqual(quest["session_hours"], 8)
        self.assertEqual(quest["union"], "non-union")
        self.assertIn("$100/8hrs", quest["pay_text"])

    def test_multi_rate_notice_collapses_to_stated_min_max(self) -> None:
        row = self.rows[2]
        self.assertEqual(row["location"], "Rutledge, GA")
        self.assertEqual(row["company"], "")
        self.assertEqual(row["salary_min"], 140.0)
        self.assertEqual(row["salary_max"], 300.0)
        self.assertEqual(row["salary_period"], "daily")
        # "experience is encouraged but not required" in the source post.
        self.assertTrue(row["first_quest_ok"])
        self.assertEqual(row["quest"]["age_min"], 9)
        self.assertEqual(row["quest"]["age_max"], 14)
        self.assertNotIn("session_hours", row["quest"])


class AuditionsFreePayExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import auditionsfree as mod
        self.mod = mod

    def test_hourly_rate(self) -> None:
        lo, hi, period, _text, _hours = self.mod._extract_pay("Pay: $12.50 p/h on set")
        self.assertEqual((lo, hi, period), (12.5, 12.5, "hourly"))

    def test_plain_labeled_amount(self) -> None:
        lo, hi, period, _text, _hours = self.mod._extract_pay("Rate: $150 for the day")
        self.assertEqual((lo, hi, period), (150.0, 150.0, None))

    def test_labeled_range(self) -> None:
        lo, hi, period, _text, _hours = self.mod._extract_pay("Pay: $100-$150 per shoot")
        self.assertEqual((lo, hi, period), (100.0, 150.0, None))

    def test_paid_without_amount_emits_nothing(self) -> None:
        lo, hi, period, text, hours = self.mod._extract_pay(
            "Compensation: Paid (rate details provided upon selection)"
        )
        self.assertEqual((lo, hi, period, text, hours), (None, None, None, "", None))

    def test_unlabeled_money_is_not_pay(self) -> None:
        lo, hi, _p, _t, _h = self.mod._extract_pay(
            "Winners get a cash prize of $20,000 and a $150,000 renovation"
        )
        self.assertIsNone(lo)
        self.assertIsNone(hi)


class AuditionsFreeAgeAndBeginnerTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import auditionsfree as mod
        self.mod = mod

    def test_age_forms(self) -> None:
        self.assertEqual(self.mod._extract_ages("seeking a female, ages 9–14, to"), (9, 14))
        self.assertEqual(self.mod._extract_ages("all genders 21-65 years of age"), (21, 65))
        self.assertEqual(self.mod._extract_ages("18 years of age or older"), (18, None))
        self.assertEqual(self.mod._extract_ages("open to ages 18+"), (18, None))
        self.assertEqual(self.mod._extract_ages("commit to 12+ hours on set"), (None, None))

    def test_first_quest_phrases(self) -> None:
        self.assertTrue(self.mod._first_quest_ok("no experience necessary"))
        self.assertTrue(self.mod._first_quest_ok("no acting experience required"))
        self.assertTrue(self.mod._first_quest_ok("experience is encouraged but not required"))
        self.assertFalse(self.mod._first_quest_ok("must have 2 years experience"))
        self.assertFalse(self.mod._first_quest_ok("experienced dancers only"))


class AuditionsFreeSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import auditionsfree as mod
        self.mod = mod

    def test_paginates_until_max_results(self) -> None:
        page1 = [_post(i) for i in range(20)]
        page2 = [_post(20 + i) for i in range(20)]
        with patch.object(self.mod, "_get_json", side_effect=[page1, page2]) as gj:
            rows = self.mod.search_auditionsfree(max_results=25)
        self.assertEqual(len(rows), 25)
        self.assertEqual(gj.call_count, 2)
        self.assertEqual(gj.call_args_list[1].kwargs["params"]["page"], 2)

    def test_single_page_when_cap_is_small(self) -> None:
        with patch.object(self.mod, "_get_json", return_value=_fixture_posts()) as gj:
            rows = self.mod.search_auditionsfree(max_results=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(gj.call_count, 1)

    def test_short_page_stops_pagination(self) -> None:
        with patch.object(self.mod, "_get_json", return_value=_fixture_posts()) as gj:
            self.mod.search_auditionsfree(max_results=50)
        self.assertEqual(gj.call_count, 1)

    def test_duplicate_links_deduped(self) -> None:
        dup = _post(1)
        with patch.object(self.mod, "_get_json", return_value=[dup, dict(dup)]):
            rows = self.mod.search_auditionsfree(max_results=50)
        self.assertEqual(len(rows), 1)

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, "nope", []):
            with patch.object(self.mod, "_get_json", return_value=bad):
                self.assertEqual(self.mod.search_auditionsfree(max_results=10), [])

    def test_bad_posts_skipped(self) -> None:
        page = ["x", None, {"title": {"rendered": "No link"}, "link": ""}, _post(7)]
        with patch.object(self.mod, "_get_json", return_value=page):
            rows = self.mod.search_auditionsfree(max_results=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Casting Call 7")

    def test_roles_are_ignored_by_design(self) -> None:
        with patch.object(self.mod, "_get_json", return_value=_fixture_posts()):
            rows = self.mod.search_auditionsfree(roles=["data engineer"], max_results=50)
        self.assertEqual(len(rows), 3)


class AuditionsFreeRegistryTest(unittest.TestCase):
    def test_registered_as_camera_quest_source(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.auditionsfree  # noqa: F401
        reg = get_registry()
        self.assertIn("auditionsfree", reg)
        meta = reg["auditionsfree"]
        self.assertEqual(meta.vertical, "camera")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))
        # Quest sources must never join the default career sweep.
        self.assertNotIn("auditionsfree", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
