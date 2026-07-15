"""Contract tests for the California Grants Portal scraper (pitch kind).

Fixture is 7 trimmed REAL records from the data.ca.gov CKAN datastore
(resource 111c8c88-21f6-453c-ae2c-b4785a0624f5; 5 captured live
2026-07-12, HTTP 200, 174 active records; 2 more captured live
2026-07-15, HTTP 200, 177 active records, for the eligibility gate):

- Tire Incentive Program: Business, exact stated range, dated deadline (keeps)
- Geothermal cost-share: Business + Individual, Ongoing, prose amounts (keeps)
- Wildfire Resilience Block Grants: no Business or Individual type (drops)
- EVITP Fund 2.0: Business, prose amounts, dated deadline (keeps)
- Boating pumpout grant: notes state "marina owners", URL is http:// (drops)
- RUST underground storage tank grant: states Business, but its own
  purpose and notes state a facility-owner compliance program (drops)
- EPIC cost-share: Individual with no Business token (keeps; proves
  the Individual side of the gate)

No active record in the live set had a past deadline, so the
past-deadline drop is proven by freezing the clock past a real record's
deadline instead of fabricating a row.
Pins: the applicant-type gate (Business or Individual, the portal's own
field), the facility-compliance drop (stated in the record's own text),
nonprofit/agency-only rows out, exact range to salary_min/max, "Up to
$X" as a ceiling never a floor, prose amounts verbatim in
quest.pay_note with no salary keys, Ongoing rows publish without
apply_by, past deadlines drop, https required. No live HTTP inside
tests.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURE = ROOT / "tests" / "fixtures" / "cagrants_records.json"

# the capture date; keeps every fixture deadline in the future
FROZEN_NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def _records() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _envelope(records: object) -> dict:
    n = len(records) if isinstance(records, list) else 0
    return {"success": True, "result": {"records": records, "total": n}}


class CaGrantsTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import cagrants as mod
        self.mod = mod

    def _search(self, payload: object, now: datetime = FROZEN_NOW, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload), \
             patch.object(self.mod, "_utcnow", return_value=now):
            return self.mod.search_cagrants(**kw)

    def test_eligible_grants_publish_from_real_capture(self) -> None:
        rows = self._search(_envelope(_records()))
        # 7 fixture records: the nonprofit/agency-only row, the two
        # facility-compliance rows (RUST tanks, marina pumpout), and the
        # http-URL row drop
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row["source"], "cagrants")
            self.assertEqual(row["vertical"], "pitch")
            self.assertTrue(row["url"].startswith("https://"))

    def test_record_maps_to_row(self) -> None:
        rows = self._search(_envelope(_records()))
        tire = next(r for r in rows if r["title"] == "Tire Incentive Program")
        self.assertEqual(
            tire["company"], "Department of Resources Recycling and Recovery"
        )
        self.assertEqual(tire["url"], "https://calrecycle.ca.gov/Tires/Grants/TIP/")
        self.assertEqual(tire["date_posted"], "2026-06-18")
        self.assertEqual(tire["quest"]["apply_by"], "2026-08-19")
        self.assertIn("Estimated available funds $3,000,000.", tire["description"])

    def test_nonprofit_only_grants_stay_out(self) -> None:
        titles = [r["title"] for r in self._search(_envelope(_records()))]
        # real fixture record whose ApplicantType names no Business or Individual
        self.assertNotIn("2026 Wildfire Resilience Block Grants", titles)

    def test_facility_compliance_grants_stay_out(self) -> None:
        # the RUST grant states ApplicantType Business, but its own purpose
        # and notes state a program for underground storage tank owners
        titles = [r["title"] for r in self._search(_envelope(_records()))]
        self.assertNotIn(
            "Replacing, Removing, or Upgrading Underground Storage Tanks Grant",
            titles,
        )

    def test_individual_eligible_grants_publish(self) -> None:
        # the EPIC cost-share names Individual and not Business, so the
        # Individual token is what keeps it
        record = next(r for r in _records() if "EPIC" in r["Title"])
        self.assertNotIn("Business", record["ApplicantType"])
        rows = self._search(_envelope(_records()))
        epic = next(r for r in rows if "EPIC" in r["title"])
        self.assertEqual(epic["company"], "CA Energy Commission")
        self.assertNotIn("apply_by", epic.get("quest", {}))

    def test_exact_stated_range_maps_to_salary(self) -> None:
        rows = self._search(_envelope(_records()))
        tire = next(r for r in rows if r["title"] == "Tire Incentive Program")
        # EstAmounts "Between $25,000 and $650,000"
        self.assertEqual(tire["salary_min"], 25000.0)
        self.assertEqual(tire["salary_max"], 650000.0)
        self.assertEqual(tire["salary_source"], "reported")
        self.assertNotIn("pay_note", tire.get("quest", {}))

    def test_up_to_is_a_ceiling_never_a_floor(self) -> None:
        fields, note = self.mod._parse_est_amounts("Up to $50,000")
        self.assertEqual(fields["salary_max"], 50000.0)
        self.assertEqual(fields["salary_source"], "reported")
        self.assertNotIn("salary_min", fields)
        self.assertIsNone(note)
        # anything beyond the exact phrasing is prose, not a number
        fields, note = self.mod._parse_est_amounts("Up to $50,000 per awardee")
        self.assertEqual(fields, {})
        self.assertEqual(note, "Up to $50,000 per awardee")

    def test_prose_amounts_ride_in_pay_note_only(self) -> None:
        rows = self._search(_envelope(_records()))
        evitp = next(r for r in rows if "Electric Vehicle" in r["title"])
        self.assertNotIn("salary_min", evitp)
        self.assertNotIn("salary_max", evitp)
        self.assertEqual(
            evitp["quest"]["pay_note"],
            "Dependant on number of submissions received, application process, etc.",
        )

    def test_ongoing_deadline_is_honest(self) -> None:
        rows = self._search(_envelope(_records()))
        geo = next(r for r in rows if "Geothermal" in r["title"])
        self.assertNotIn("apply_by", geo.get("quest", {}))
        self.assertIn("ongoing basis", geo["description"].lower())

    def test_past_deadline_rows_drop(self) -> None:
        # EVITP closes 2026-07-31; Tire closes 2026-08-19; the Geothermal
        # and EPIC cost-shares are Ongoing and never do
        later = datetime(2026, 8, 5, tzinfo=timezone.utc)
        titles = [r["title"] for r in self._search(_envelope(_records()), now=later)]
        self.assertEqual(len(titles), 3)
        self.assertNotIn(
            "The Electric Vehicle Infrastructure Training Program Fund (EVITP Fund) 2.0",
            titles,
        )
        self.assertIn("Tire Incentive Program", titles)

    def test_http_grant_urls_drop(self) -> None:
        titles = [r["title"] for r in self._search(_envelope(_records()))]
        self.assertFalse(any("Boating and Waterways" in t for t in titles))
        # the real record also trips the facility gate ("marina owners"
        # in its notes), so prove the https rule on its own: with that
        # text cleared the http URL still drops it, and https would not
        record = next(r for r in _records() if "Boating and Waterways" in r["Title"])
        cleared = {**record, "ApplicantTypeNotes": None}
        with patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW):
            self.assertIsNone(self.mod._normalize_record(cleared))
            https_url = str(cleared["GrantURL"]).replace("http://", "https://")
            self.assertIsNotNone(
                self.mod._normalize_record({**cleared, "GrantURL": https_url})
            )

    def test_query_targets_the_active_dataset(self) -> None:
        captured: list[dict] = []

        def fake_get_json(url, params=None, **_kw):
            captured.append(dict(params or {}))
            return _envelope(_records())

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json), \
             patch.object(self.mod, "_utcnow", return_value=FROZEN_NOW):
            self.mod.search_cagrants()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["resource_id"], self.mod._RESOURCE_ID)
        self.assertEqual(json.loads(captured[0]["filters"]), {"Status": "active"})

    def test_bad_payloads_return_empty(self) -> None:
        for bad in (
            None,
            {},
            "x",
            42,
            [],
            {"success": False},
            {"success": True, "result": {}},
            {"success": True, "result": {"records": "x"}},
            _envelope([None, "x", 42]),
        ):
            self.assertEqual(self._search(bad), [])

    def test_max_results_caps_rows(self) -> None:
        rows = self._search(_envelope(_records()), max_results=1)
        self.assertEqual(len(rows), 1)


class CaGrantsRegistryTest(unittest.TestCase):
    def test_registered_as_pitch_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.cagrants  # noqa: F401

        reg = get_registry()
        self.assertIn("cagrants", reg)
        meta = reg["cagrants"]
        self.assertEqual(meta.vertical, "pitch")
        self.assertEqual(meta.display_name, "California Grants Portal")
        self.assertFalse(meta.enabled_by_default)
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        self.assertIsNone(meta.stale_after_days)
        # apply pages span many *.ca.gov subdomains plus vendor hosts, so no
        # host gate (bankrewards precedent); the scraper requires https instead
        self.assertIsNone(meta.allowed_url_hosts)
        self.assertTrue(callable(meta.search_fn))
        # Quest scrapers never join the default career sweep.
        self.assertNotIn("cagrants", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
