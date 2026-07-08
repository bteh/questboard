"""Contract tests for the ClinicalTrials.gov quest scraper (vertical "study").

The fixture is a trimmed REAL response from the v2 studies endpoint (probed
live 2026-07-08, HTTP 200): three recruiting healthy-volunteer studies kept,
bulk modules and site contacts stripped. These tests pin the study-to-row
mapping, the no-salary-keys rule (the API has no compensation field), the
quest extras (age bounds, healthy_volunteers, phase), nearest-site selection,
geo/query param construction, pagination, graceful degradation, and registry
registration under the study vertical.
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

FIXTURE = ROOT / "tests" / "fixtures" / "clinicaltrials_studies.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class ClinicalTrialsHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import clinicaltrials as mod
        self.mod = mod

    def test_age_years(self) -> None:
        self.assertEqual(self.mod._age_years("18 Years"), 18)
        self.assertEqual(self.mod._age_years("100 Years"), 100)
        self.assertEqual(self.mod._age_years("6 Months"), 0)
        self.assertIsNone(self.mod._age_years(None))
        self.assertIsNone(self.mod._age_years(""))
        self.assertIsNone(self.mod._age_years("N/A"))

    def test_phase_label(self) -> None:
        self.assertEqual(self.mod._phase_label(["PHASE2"]), "Phase 2")
        self.assertEqual(self.mod._phase_label(["PHASE1", "PHASE2"]), "Phase 1/Phase 2")
        self.assertEqual(self.mod._phase_label(["EARLY_PHASE1"]), "Early Phase 1")
        self.assertIsNone(self.mod._phase_label(["NA"]))
        self.assertIsNone(self.mod._phase_label(None))

    def test_format_location_us_uses_state(self) -> None:
        site = {"city": "Ann Arbor", "state": "Michigan", "country": "United States"}
        self.assertEqual(self.mod._format_location(site), "Ann Arbor, Michigan")

    def test_format_location_non_us_uses_country(self) -> None:
        site = {"city": "Toronto", "state": "Ontario", "country": "Canada"}
        self.assertEqual(self.mod._format_location(site), "Toronto, Canada")


class ClinicalTrialsParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import clinicaltrials as mod
        self.mod = mod

    def _search(self, payload: object, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=payload):
            return self.mod.search_clinicaltrials(**kw)

    def test_parses_fixture_studies(self) -> None:
        rows = self._search(_fixture())
        self.assertEqual(len(rows), 3)
        r = rows[0]
        self.assertEqual(r["title"], "Longitudinal Oral Microbiome Sampling for BE")
        self.assertEqual(r["company"], "Columbia University")
        self.assertEqual(r["url"], "https://clinicaltrials.gov/study/NCT05133102")
        self.assertEqual(r["source"], "clinicaltrials")
        self.assertEqual(r["vertical"], "study")
        self.assertTrue(r["is_rolling"])
        self.assertTrue(r["first_quest_ok"])
        self.assertEqual(r["date_posted"], "2021-11-24")
        self.assertIn("longitudinal cohort study", r["description"])

    def test_never_emits_salary_keys(self) -> None:
        # The v2 API has no compensation field, so pay must never be promised.
        for row in self._search(_fixture()):
            for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
                self.assertNotIn(key, row)

    def test_quest_extras(self) -> None:
        rows = self._search(_fixture())
        q0 = rows[0]["quest"]
        self.assertTrue(q0["healthy_volunteers"])
        self.assertEqual(q0["age_min"], 18)
        self.assertNotIn("age_max", q0)   # protocol states no maximum
        self.assertNotIn("phase", q0)     # observational study, no phase
        self.assertEqual(q0["study_type"], "OBSERVATIONAL")
        self.assertEqual(q0["headcount"], 275)

        q1 = rows[1]["quest"]
        self.assertEqual(q1["age_min"], 18)
        self.assertEqual(q1["age_max"], 100)
        self.assertEqual(q1["phase"], "Phase 3")

        q2 = rows[2]["quest"]
        self.assertNotIn("age_min", q2)   # protocol states no age bounds
        self.assertNotIn("age_max", q2)
        self.assertEqual(q2["phase"], "Phase 2")

    def test_nearest_site_without_reference_point(self) -> None:
        # First recruiting site in protocol order wins when no lat/lon given.
        rows = self._search(_fixture())
        self.assertEqual(rows[0]["location"], "Ann Arbor, Michigan")

    def test_nearest_site_with_reference_point(self) -> None:
        # Near NYC the Columbia site (2nd in protocol order) is closest.
        rows = self._search(_fixture(), lat=40.7128, lon=-74.0060)
        self.assertEqual(rows[0]["location"], "New York, New York")

    def test_date_posted_omitted_when_source_states_none(self) -> None:
        payload = copy.deepcopy(_fixture())
        del payload["studies"][0]["protocolSection"]["statusModule"]["studyFirstPostDateStruct"]
        rows = self._search(payload)
        self.assertNotIn("date_posted", rows[0])
        self.assertEqual(rows[1]["date_posted"], "2021-12-13")

    def test_skips_study_without_nct_id_or_title(self) -> None:
        payload = copy.deepcopy(_fixture())
        del payload["studies"][0]["protocolSection"]["identificationModule"]["nctId"]
        payload["studies"][1]["protocolSection"]["identificationModule"]["briefTitle"] = ""
        rows = self._search(payload)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://clinicaltrials.gov/study/NCT04936529")

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, {"studies": None}, {"studies": []}, [], "nope"):
            self.assertEqual(self._search(bad), [])


class ClinicalTrialsRequestTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import clinicaltrials as mod
        self.mod = mod

    def test_request_params(self) -> None:
        captured: list[dict] = []

        def fake_get_json(url, params=None, **kw):
            captured.append(dict(params or {}))
            return _fixture()

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            self.mod.search_clinicaltrials(
                query="sleep", lat=40.7128, lon=-74.006, radius_miles=50, max_results=10,
            )
        p = captured[0]
        self.assertEqual(p["filter.advanced"], "AREA[HealthyVolunteers]true")
        self.assertEqual(p["filter.overallStatus"], "RECRUITING")
        self.assertEqual(p["filter.geo"], "distance(40.7128,-74.006,50mi)")
        self.assertEqual(p["query.term"], "sleep")
        self.assertEqual(p["pageSize"], "10")

    def test_no_geo_filter_without_both_coordinates(self) -> None:
        captured: list[dict] = []

        def fake_get_json(url, params=None, **kw):
            captured.append(dict(params or {}))
            return _fixture()

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            self.mod.search_clinicaltrials(lat=40.7128)
        self.assertNotIn("filter.geo", captured[0])
        self.assertNotIn("query.term", captured[0])

    def test_paginates_via_next_page_token(self) -> None:
        page1 = _fixture()
        page1["nextPageToken"] = "TOKEN123"
        page2 = _fixture()
        pages = [page1, page2]
        captured: list[dict] = []

        def fake_get_json(url, params=None, **kw):
            captured.append(dict(params or {}))
            return pages[len(captured) - 1]

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            rows = self.mod.search_clinicaltrials(max_results=50)
        self.assertEqual(len(rows), 6)
        self.assertEqual(len(captured), 2)
        self.assertNotIn("pageToken", captured[0])
        self.assertEqual(captured[1]["pageToken"], "TOKEN123")

    def test_max_results_caps_and_stops_paginating(self) -> None:
        page1 = _fixture()
        page1["nextPageToken"] = "TOKEN123"
        calls: list[int] = []

        def fake_get_json(url, params=None, **kw):
            calls.append(1)
            return page1

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            rows = self.mod.search_clinicaltrials(max_results=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(calls), 1)


class ClinicalTrialsRegistryTest(unittest.TestCase):
    def test_registered_as_study_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.clinicaltrials  # noqa: F401

        reg = get_registry()
        self.assertIn("clinicaltrials", reg)
        meta = reg["clinicaltrials"]
        self.assertEqual(meta.vertical, "study")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))
        # Quest scrapers never join the default career sweep.
        self.assertNotIn("clinicaltrials", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
