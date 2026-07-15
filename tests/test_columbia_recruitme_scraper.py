"""Contract tests for the Columbia RecruitMe scraper (body kind).

Fixtures are trimmed REAL pages captured live 2026-07-14 (HTTP 200):
``columbia_recruitme_search.html`` keeps three Currently Recruiting
search-item divs verbatim from https://recruit.cumc.columbia.edu/search
plus one Closed item from ?page=1; ``columbia_recruitme_study.html`` is
the detail page for study 3022, whose summary states "earn up to $300".
Pins: closed items drop, comp renders only when the detail page states
it ("up to" is a ceiling ONLY), the verbatim pay sentence rides in
quest.pay_note, urls stay on recruit.cumc.columbia.edu, detail fetches
are capped at max_results, and no row ever carries date_posted (the
source states no dates). No live HTTP inside tests.
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

INDEX_FIXTURE = ROOT / "tests" / "fixtures" / "columbia_recruitme_search.html"
DETAIL_FIXTURE = ROOT / "tests" / "fixtures" / "columbia_recruitme_study.html"

DETAIL_URL = "https://recruit.cumc.columbia.edu/studyinfopage/3022"
# real marker, verbatim from live studyinfopage/1478 (a closed study)
CLOSED_MARKER = '<div class="closed_to_enrollment">This study is closed</div>'


class ColumbiaRecruitmeTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import columbia_recruitme as mod
        self.mod = mod
        self.index_html = INDEX_FIXTURE.read_text(encoding="utf-8")
        self.detail_html = DETAIL_FIXTURE.read_text(encoding="utf-8")

    def _search(self, index_html, detail_html=None, **kw) -> list[dict]:
        """Run the scraper with page 0 = index_html and one detail page mocked.

        Only DETAIL_URL gets detail_html; every other detail fetch fails
        (returns None), which must degrade to listing data, never invent pay.
        """
        if detail_html is None:
            detail_html = self.detail_html

        def fetch_page(page):
            return index_html if page == 0 else None

        def fetch_detail(url):
            return detail_html if url == DETAIL_URL else None

        with patch.object(self.mod, "_fetch_search_page", side_effect=fetch_page) as self.page_mock, \
             patch.object(self.mod, "_fetch_detail", side_effect=fetch_detail) as self.detail_mock, \
             patch.object(self.mod.time, "sleep"):
            return self.mod.search_columbia_recruitme(**kw)

    def test_parses_recruiting_items_into_body_rows(self) -> None:
        rows = self._search(self.index_html)
        # fixture holds 4 items; the Closed one (study 1041) drops
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["vertical"], "body")
            self.assertEqual(row["source"], "columbia_recruitme")
            self.assertEqual(row["location"], "New York, NY")
            self.assertEqual(row["company"], "Columbia University Irving Medical Center")
            self.assertTrue(row["title"])
            self.assertTrue(row["is_rolling"])

    def test_urls_stay_on_recruitme(self) -> None:
        rows = self._search(self.index_html)
        for row in rows:
            self.assertTrue(
                row["url"].startswith("https://recruit.cumc.columbia.edu/studyinfopage/")
            )
        urls = [row["url"] for row in rows]
        self.assertNotIn("https://recruit.cumc.columbia.edu/studyinfopage/1041", urls)

    def test_comp_only_when_the_detail_page_states_it(self) -> None:
        rows = self._search(self.index_html)
        by_url = {row["url"]: row for row in rows}
        paid = by_url[DETAIL_URL]
        # "participants can earn up to $300" is a ceiling ONLY, never a floor
        self.assertEqual(paid["salary_max"], 300.0)
        self.assertEqual(paid["salary_source"], "reported")
        self.assertNotIn("salary_min", paid)
        for url, row in by_url.items():
            if url == DETAIL_URL:
                continue
            self.assertNotIn("salary_min", row)
            self.assertNotIn("salary_max", row)
            self.assertNotIn("salary_source", row)

    def test_pay_note_carries_the_verbatim_sentence(self) -> None:
        rows = self._search(self.index_html)
        by_url = {row["url"]: row for row in rows}
        self.assertEqual(
            by_url[DETAIL_URL]["quest"]["pay_note"],
            "We are conducting a study on depression and suicide risk, "
            "and participants can earn up to $300 for taking part.",
        )
        for url, row in by_url.items():
            if url != DETAIL_URL:
                self.assertNotIn("pay_note", row.get("quest", {}))

    def test_detail_fields_land_in_quest(self) -> None:
        rows = self._search(self.index_html)
        quest = {row["url"]: row for row in rows}[DETAIL_URL]["quest"]
        self.assertEqual(quest["sponsor"], "National Institute of Mental Health")
        self.assertEqual(quest["study_length"], "3 Weeks")
        self.assertEqual(quest["clinic_visits"], "4")
        self.assertEqual(quest["irb_number"], "AAAV4037")
        self.assertEqual(quest["investigator"], "Sarah Herzog, PhD")
        # "Male and Female Patients" means everyone; the row says nothing
        self.assertNotIn("sex", quest)

    def test_healthy_volunteers_flag_from_stated_condition(self) -> None:
        rows = self._search(self.index_html)
        by_url = {row["url"]: row for row in rows}
        healthy = by_url["https://recruit.cumc.columbia.edu/studyinfopage/3090"]
        self.assertTrue(healthy["first_quest_ok"])
        self.assertTrue(healthy["quest"]["healthy_volunteers"])
        self.assertEqual(healthy["quest"]["condition"], "Healthy Volunteers")
        cidp = by_url["https://recruit.cumc.columbia.edu/studyinfopage/3091"]
        self.assertFalse(cidp["first_quest_ok"])
        self.assertNotIn("healthy_volunteers", cidp["quest"])
        self.assertEqual(cidp["quest"]["condition"], "Neurological Disorders")

    def test_description_prefers_the_full_detail_summary(self) -> None:
        rows = self._search(self.index_html)
        by_url = {row["url"]: row for row in rows}
        # 3022's detail summary replaces the truncated listing teaser
        desc = by_url[DETAIL_URL]["description"]
        self.assertTrue(desc.startswith("We are conducting a study on depression"))
        self.assertNotIn("…", desc)
        self.assertLessEqual(len(desc), 403)
        # 3090's detail fetch fails, so its teaser stays
        teaser = by_url["https://recruit.cumc.columbia.edu/studyinfopage/3090"]["description"]
        self.assertTrue(teaser.startswith("This is a research study to understand"))

    def test_detail_closed_marker_outranks_the_listing(self) -> None:
        closed_detail = self.detail_html.replace("</body>", CLOSED_MARKER + "</body>")
        rows = self._search(self.index_html, detail_html=closed_detail)
        urls = [row["url"] for row in rows]
        self.assertNotIn(DETAIL_URL, urls)
        self.assertEqual(len(rows), 2)

    def test_no_row_ever_carries_date_posted(self) -> None:
        # the source states no dates; inventing one would fake freshness
        for row in self._search(self.index_html):
            self.assertNotIn("date_posted", row)

    def test_max_results_caps_rows_and_detail_fetches(self) -> None:
        rows = self._search(self.index_html, max_results=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.detail_mock.call_count, 1)

    def test_all_closed_page_stops_the_pager(self) -> None:
        closed_index = self.index_html.replace("Currently Recruiting", "Closed")
        rows = self._search(closed_index)
        self.assertEqual(rows, [])
        # recruiting sorts first, so one all-closed page ends the crawl
        self.assertEqual(self.page_mock.call_count, 1)

    def test_empty_and_bad_html_return_empty(self) -> None:
        self.assertEqual(self._search(""), [])
        self.assertEqual(self._search("<html><body>maintenance</body></html>"), [])
        self.assertEqual(self._search("<div class='search-item'>junk</div>"), [])


class StatedCompTest(unittest.TestCase):
    """Pay parsing pinned on real sentences captured live 2026-07-14."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers import columbia_recruitme as mod
        self.comp = mod._stated_comp

    def test_up_to_is_a_ceiling_only(self) -> None:
        # studyinfopage/3029
        out = self.comp("You can earn up to $220 for your participation.")
        self.assertEqual(out, {"salary_max": 220.0, "salary_source": "reported"})

    def test_single_hourly_rate(self) -> None:
        # search teaser, page 0
        out = self.comp("Participants earn $25 per hour.")
        self.assertEqual(out, {
            "salary_min": 25.0,
            "salary_max": 25.0,
            "salary_period": "hourly",
            "salary_source": "reported",
        })

    def test_half_range_between_emits_nothing(self) -> None:
        # studyinfopage/2875 states no upper bound
        out = self.comp("Study participants earn between $15/hour for their time.")
        self.assertEqual(out, {})

    def test_per_visit_schedule_emits_nothing(self) -> None:
        # studyinfopage/1478: a total here would be invented
        out = self.comp(
            "You will be compensated $150 for the injection or infusion visits; "
            "$50 or $75 for visits involving blood draw and $25 for visits "
            "where no blood is drawn."
        )
        self.assertEqual(out, {})

    def test_no_dollar_amount_emits_nothing(self) -> None:
        # studyinfopage/1340 says only "You will be compensated for the visit."
        self.assertEqual(self.comp("You will be compensated for the visit."), {})


class AgesAndSexTest(unittest.TestCase):
    """Eligibility parsing pinned on real strings captured live 2026-07-14."""

    def setUp(self) -> None:
        from job_finder.tools.scrapers import columbia_recruitme as mod
        self.mod = mod

    def test_ages_from_years_old_phrasing(self) -> None:
        # studyinfopage/1478
        self.assertEqual(
            self.mod._ages("healthy, HIV-negative individuals 18 to 50 years old"),
            (18, 50),
        )
        # studyinfopage/1340
        self.assertEqual(
            self.mod._ages("We are looking for individuals 18 to 65 years old"),
            (18, 65),
        )

    def test_durations_are_not_ages(self) -> None:
        # studyinfopage/1478: a study length, not an age band
        self.assertIsNone(
            self.mod._ages("you will come to clinic for 19 visits over little more than 2 years")
        )
        # studyinfopage/2875
        self.assertIsNone(
            self.mod._ages("The study is typically expected to take 1 - 4 hours in total.")
        )

    def test_sex_only_when_restricted(self) -> None:
        # values verbatim from studyinfopage/3022 and /2556
        self.assertEqual(self.mod._sex("Male and Female Patients"), "")
        self.assertEqual(self.mod._sex("Female Patients Only"), "Female")
        self.assertEqual(self.mod._sex(""), "")


class RegistryTest(unittest.TestCase):
    def test_registered_as_body_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.columbia_recruitme  # noqa: F401
        reg = get_registry()
        self.assertIn("columbia_recruitme", reg)
        meta = reg["columbia_recruitme"]
        self.assertEqual(meta.vertical, "body")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("recruit.cumc.columbia.edu",))
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_not_in_default_career_sweep(self) -> None:
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.columbia_recruitme  # noqa: F401
        self.assertNotIn("columbia_recruitme", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
