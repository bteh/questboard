"""Contract tests for the FocusGroups.org quest scraper (vertical "study").

The fixture is a trimmed REAL /all/ listing page (probed live 2026-07-08,
HTTP 200 on the apex host; www 526s at Cloudflare): seven representative
study cards kept verbatim plus the header nav /category/ links, bulk
stripped. These tests pin the card-to-row mapping, the strict pay-chip parse
(explicit figures only; "Varies", "$60 p/yr" and "up to $200+" must emit no
salary keys), the posted-date conversion, the online-stated location rule,
quest extras, dedup/cap, graceful degradation, and registry registration
under the study vertical.
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

FIXTURE = ROOT / "tests" / "fixtures" / "focusgroups_org_all.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class PayParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import focusgroups_org as mod
        self.mod = mod

    def test_flat(self) -> None:
        self.assertEqual(self.mod._parse_pay("$38"), (38.0, 38.0))
        self.assertEqual(self.mod._parse_pay("$1,200"), (1200.0, 1200.0))

    def test_range(self) -> None:
        self.assertEqual(self.mod._parse_pay("$100-$125"), (100.0, 125.0))
        self.assertEqual(self.mod._parse_pay("$100 - $400"), (100.0, 400.0))

    def test_up_to(self) -> None:
        self.assertEqual(self.mod._parse_pay("up to $1500"), (None, 1500.0))
        self.assertEqual(self.mod._parse_pay("up to $1,200"), (None, 1200.0))

    def test_not_explicit_pay(self) -> None:
        for chip in ("Varies", "$60 p/yr", "up to $200+", "", "TBD", "$"):
            self.assertEqual(self.mod._parse_pay(chip), (None, None), chip)


class PostedDateTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import focusgroups_org as mod
        self.mod = mod

    def test_two_digit_year(self) -> None:
        self.assertEqual(self.mod._posted_to_iso("Posted: 07/08/26"), "2026-07-08")

    def test_four_digit_year(self) -> None:
        self.assertEqual(self.mod._posted_to_iso("Posted: 10/04/2024"), "2024-10-04")

    def test_absent_or_odd(self) -> None:
        self.assertEqual(self.mod._posted_to_iso(""), "")
        self.assertEqual(self.mod._posted_to_iso("Posted: soon"), "")
        self.assertEqual(self.mod._posted_to_iso("Posted: 13/40/26"), "")


class FixtureParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import focusgroups_org as mod
        self.mod = mod
        self.cards = mod._parse_cards(_html())
        self.rows = [r for r in map(mod._normalize_card, self.cards) if r]
        self.by_title = {r["title"]: r for r in self.rows}

    def test_parses_all_cards_and_skips_nav_links(self) -> None:
        # 7 study cards; the header nav /category/ links must not become rows.
        self.assertEqual(len(self.rows), 7)

    def test_row_contract(self) -> None:
        for r in self.rows:
            self.assertEqual(r["source"], "focusgroups_org")
            self.assertEqual(r["vertical"], "study")
            self.assertEqual(r["company"], "FocusGroups.org")
            self.assertTrue(r["url"].startswith("https://focusgroups.org/category/"))
            self.assertTrue(r["first_quest_ok"])
            self.assertIsInstance(r["quest"], dict)

    def test_flat_pay_card(self) -> None:
        r = self.by_title["Research Study on Business Tools - $38"]
        self.assertEqual(r["salary_min"], 38.0)
        self.assertEqual(r["salary_max"], 38.0)
        self.assertEqual(r["salary_period"], "session")
        self.assertEqual(r["salary_source"], "reported")
        self.assertEqual(r["date_posted"], "2026-07-08")
        self.assertEqual(r["date_confidence"], "exact")

    def test_range_pay_card(self) -> None:
        r = self.by_title["Personal Finances Focus Group - $100+"]
        self.assertEqual(r["salary_min"], 100.0)
        self.assertEqual(r["salary_max"], 125.0)
        self.assertEqual(r["quest"]["category"], "Focus Group")
        self.assertEqual(r["quest"]["topic"], "Finance")
        # No "online" stated on this card: format unknown, location empty.
        self.assertEqual(r["location"], "")
        self.assertNotIn("format", r["quest"])

    def test_up_to_pay_card(self) -> None:
        r = self.by_title["Clinical Trial on Type 2 Diabetes - up to $1500"]
        # "up to $X" has no floor: the key is omitted, never salary_min=None.
        self.assertNotIn("salary_min", r)
        self.assertEqual(r["salary_max"], 1500.0)
        self.assertEqual(r["salary_source"], "reported")
        self.assertTrue(r["quest"]["featured"])

    def test_no_none_valued_salary_keys_on_any_row(self) -> None:
        # Regression: "up to $X" chips used to emit salary_min=None, which
        # survives dict merges downstream and reads as stated pay data.
        for r in self.rows:
            for key in ("salary_min", "salary_max"):
                if key in r:
                    self.assertIsNotNone(r[key], f"{r['title']}: {key} is None")

    def test_varies_card_emits_no_salary_keys(self) -> None:
        r = self.by_title["Streaming & Mobile Usage Habits"]
        for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
            self.assertNotIn(key, r)
        self.assertNotIn("pay_text", r["quest"])   # "Varies" is not a figure

    def test_odd_chips_keep_raw_text_but_no_salary(self) -> None:
        nielsen = self.by_title["Nielsen Phone Usage Study - $60 p/yr"]
        freecash = self.by_title["FreeCash Rewards & Surveys"]
        for r, chip in ((nielsen, "$60 p/yr"), (freecash, "up to $200+")):
            self.assertNotIn("salary_min", r)
            self.assertNotIn("salary_source", r)
            self.assertEqual(r["quest"]["pay_text"], chip)

    def test_online_stated_sets_location_and_format(self) -> None:
        r = self.by_title["Research Study on Fatty Liver Disease - $125"]
        self.assertEqual(r["quest"]["category"], "Online Survey")
        self.assertEqual(r["location"], "Online")
        self.assertEqual(r["quest"]["format"], "online")

    def test_placeholder_topic_pill_is_dropped(self) -> None:
        r = self.by_title["FreeCash Rewards & Surveys"]   # topic pill is "None"
        self.assertNotIn("topic", r["quest"])
        self.assertNotIn("Topic:", r["description"])

    def test_html_entities_unescaped_in_title(self) -> None:
        self.assertIn("FreeCash Rewards & Surveys", self.by_title)

    def test_description_carries_structured_chips(self) -> None:
        r = self.by_title["Research Study on Business Tools - $38"]
        self.assertIn("Category: Unmoderated Study", r["description"])
        self.assertIn("Topic: Business", r["description"])
        self.assertIn("Pay: $38", r["description"])

    def test_deep_link_is_the_detail_page(self) -> None:
        r = self.by_title["Research Study on Business Tools - $38"]
        self.assertEqual(
            r["url"],
            "https://focusgroups.org/category/unmoderated-studies/"
            "research-study-on-business-tools-38/4a1d72ff-c691-42b4-a0ef-a4df3414999b/",
        )


class SearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import focusgroups_org as mod
        self.mod = mod

    def test_search_parses_fixture(self) -> None:
        with patch.object(self.mod, "_fetch_listing", return_value=_html()):
            rows = self.mod.search_focusgroups_org()
        self.assertEqual(len(rows), 7)

    def test_max_results_caps(self) -> None:
        with patch.object(self.mod, "_fetch_listing", return_value=_html()):
            rows = self.mod.search_focusgroups_org(max_results=3)
        self.assertEqual(len(rows), 3)

    def test_roles_are_ignored(self) -> None:
        # Studies are not role-titled; a career-role filter must not zero them.
        with patch.object(self.mod, "_fetch_listing", return_value=_html()):
            rows = self.mod.search_focusgroups_org(roles=["data engineer"])
        self.assertEqual(len(rows), 7)

    def test_fetch_failure_returns_empty(self) -> None:
        with patch.object(self.mod, "_fetch_listing", return_value=None):
            self.assertEqual(self.mod.search_focusgroups_org(), [])

    def test_dedup_by_url(self) -> None:
        html = _html()
        # Duplicate the whole studies block: every card appears twice.
        with patch.object(self.mod, "_fetch_listing", return_value=html + html):
            rows = self.mod.search_focusgroups_org()
        self.assertEqual(len(rows), 7)


class RegistryTest(unittest.TestCase):
    def test_registered_as_study_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.focusgroups_org  # noqa: F401
        reg = get_registry()
        self.assertIn("focusgroups_org", reg)
        meta = reg["focusgroups_org"]
        self.assertEqual(meta.vertical, "study")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_not_in_default_career_sweep(self) -> None:
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.focusgroups_org  # noqa: F401
        self.assertNotIn("focusgroups_org", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
