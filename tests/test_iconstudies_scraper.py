"""Contract tests for the ICON Clinical Studies scraper (body kind).

Fixture is a trimmed REAL all-studies page from
https://iconstudies.com/All-Clinical-Research-Studies/ (captured live
2026-07-10, HTTP 200; three studies-card divs kept verbatim, plus card
806's natural page duplicate to pin dedup). Pins: title = population +
protocol, the apply-form URL is the row URL, "Up to $13500" maps to a
ceiling ONLY, the age band lands in quest, non-enrolling cards drop, and
no row ever carries date_posted (the source states no dates). No live
HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "iconstudies_list.html"


class IconStudiesTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import iconstudies as mod
        self.mod = mod
        self.html = FIXTURE.read_text(encoding="utf-8")

    def _search(self, html, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_listing", return_value=html):
            return self.mod.search_iconstudies(**kw)

    def test_parses_cards_into_body_rows(self) -> None:
        rows = self._search(self.html)
        # fixture holds 4 cards but card 806 appears twice (the real page
        # repeats cards across sections); dedup by URL keeps 3 studies
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["vertical"], "body")
            self.assertEqual(row["source"], "iconstudies")
            self.assertTrue(row["title"])

    def test_title_is_population_plus_protocol(self) -> None:
        rows = self._search(self.html)
        lenexa = rows[1]
        self.assertEqual(lenexa["title"], "Healthy Participants (Study 3954/0090)")

    def test_row_url_is_the_application_form(self) -> None:
        rows = self._search(self.html)
        self.assertEqual(
            rows[1]["url"],
            "https://iconstudies.com/Lenexa/Clinical-Research-Study/806/Application/",
        )
        for row in rows:
            self.assertTrue(row["url"].startswith("https://iconstudies.com/"))
            self.assertTrue(row["url"].endswith("/Application/"))

    def test_location_and_regimen_description(self) -> None:
        rows = self._search(self.html)
        lenexa = rows[1]
        self.assertEqual(lenexa["location"], "Lenexa, KS")
        self.assertEqual(
            lenexa["description"],
            "Participation in this study includes 1 screening visit, "
            "1 stay of 18 nights and 2 outpatient visits.",
        )

    def test_ages_land_in_quest(self) -> None:
        rows = self._search(self.html)
        quest = rows[1]["quest"]
        self.assertEqual(quest["age_min"], 18)
        self.assertEqual(quest["age_max"], 65)

    def test_up_to_is_a_ceiling_never_a_floor(self) -> None:
        rows = self._search(self.html)
        lenexa = rows[1]
        self.assertEqual(lenexa["salary_max"], 13500.0)
        self.assertEqual(lenexa["salary_source"], "reported")
        self.assertNotIn("salary_min", lenexa)
        for row in rows:
            self.assertNotIn("salary_min", row)

    def test_sex_stored_only_when_restricted(self) -> None:
        rows = self._search(self.html)
        # card 806: "Male/Female" means everyone; the row says nothing
        self.assertNotIn("sex", rows[1].get("quest", {}))
        # card 794 (Salt Lake City): the source states "Female"
        slc = rows[2]
        self.assertEqual(slc["location"], "Salt Lake City, UT")
        self.assertEqual(slc["quest"]["sex"], "Female")

    def test_non_enrolling_card_is_dropped(self) -> None:
        # flip one REAL card's status pill to simulate a closed study
        closed = self.html.replace("Enrolling", "Coming Soon", 1)
        rows = self._search(closed)
        self.assertEqual(len(rows), 2)

    def test_no_row_ever_carries_date_posted(self) -> None:
        # the source states no dates; inventing one would fake freshness
        for row in self._search(self.html):
            self.assertNotIn("date_posted", row)

    def test_empty_and_bad_html_return_empty(self) -> None:
        self.assertEqual(self._search(""), [])
        self.assertEqual(self._search(None), [])
        self.assertEqual(self._search("<html><body>maintenance</body></html>"), [])
        self.assertEqual(self._search("<div class='studies-card'>junk</div>"), [])

    def test_max_results_cap(self) -> None:
        rows = self._search(self.html, max_results=1)
        self.assertEqual(len(rows), 1)


class RegistryTest(unittest.TestCase):
    def test_registered_as_body_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        import job_finder.tools.scrapers.iconstudies  # noqa: F401
        reg = get_registry()
        self.assertIn("iconstudies", reg)
        meta = reg["iconstudies"]
        self.assertEqual(meta.vertical, "body")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertEqual(meta.allowed_url_hosts, ("iconstudies.com",))
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))

    def test_not_in_default_career_sweep(self) -> None:
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.iconstudies  # noqa: F401
        self.assertNotIn("iconstudies", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
