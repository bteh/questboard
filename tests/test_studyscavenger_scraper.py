"""Contract tests for the Study Scavenger scraper (body kind).

Fixture is a trimmed REAL response from
https://studyscavenger.com/wp-json/wp/v2/posts (captured live 2026-07-09,
HTTP 200) plus one variant with no stated compensation. Pins: pay comes
only from an explicit compensation sentence ("compensation up to $7,750"
maps to a ceiling, never a floor), no-comp posts carry no pay at all,
and the parenthesized City, ST in titles becomes the location.
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

FIXTURE = ROOT / "tests" / "fixtures" / "studyscavenger_posts.json"


def _load_fixture() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class StudyScavengerTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import studyscavenger as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_studyscavenger(**kw)

    def test_parses_posts_into_body_rows(self) -> None:
        rows = self._search(_load_fixture())
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row["vertical"], "body")
            self.assertTrue(row["url"].startswith("https://studyscavenger.com/"))
            self.assertNotIn("​", row["title"])

    def test_up_to_compensation_is_a_ceiling_never_a_floor(self) -> None:
        rows = self._search(_load_fixture())
        paid = next(r for r in rows if r.get("salary_max"))
        self.assertEqual(paid["salary_max"], 7750.0)
        self.assertNotIn("salary_min", paid)
        self.assertEqual(paid["salary_source"], "reported")

    def test_no_stated_comp_means_no_pay_fields(self) -> None:
        rows = self._search(_load_fixture())
        nocomp = next(r for r in rows if "No Stated Comp" in r["title"])
        self.assertNotIn("salary_min", nocomp)
        self.assertNotIn("salary_max", nocomp)

    def test_city_state_in_title_becomes_location(self) -> None:
        rows = self._search(_load_fixture())
        lenexa = next(r for r in rows if "Lenexa" in r["title"])
        self.assertEqual(lenexa["location"], "Lenexa, KS")

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, "x", 42):
            self.assertEqual(self._search(bad), [])

    def test_divi_shortcodes_are_stripped_from_description(self) -> None:
        # studyscavenger.com is a Divi/WordPress site; content.rendered carries
        # page-builder shortcodes that aren't HTML tags. They must not leak into
        # the description; the inner text must survive.
        post = {
            "title": {"rendered": "COPD Study - Lenexa, KS"},
            "link": "https://studyscavenger.com/study/copd/",
            "content": {"rendered": (
                '[et_pb_section fb_built="1" _builder_version="4.16"]'
                "[et_pb_row][et_pb_column][et_pb_text]"
                "Seeking adults 40+ with COPD. Compensation up to $500 for 3 visits."
                "[/et_pb_text][/et_pb_column][/et_pb_row][/et_pb_section]"
            )},
        }
        row = self.mod._normalize_post(post)
        self.assertIsNotNone(row)
        desc = row["description"]
        self.assertNotIn("et_pb_", desc)
        self.assertNotIn("[", desc)
        self.assertIn("Seeking adults 40+ with COPD", desc)
        self.assertEqual(row["salary_max"], 500.0)  # comp still parses from clean text


if __name__ == "__main__":
    unittest.main()
