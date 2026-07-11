"""Contract tests for the Trialmed (PPD clinics) scraper (body kind).

Fixtures are trimmed REAL responses from
https://trialmed.com/wp-json/wp/v2/studies and /clinics (captured live
2026-07-10, HTTP 200, x-wp-total 60): five studies (enrolling US with
"Up to $X", coming-soon, enrolling with varies-by-study pay, enrolling
multi-clinic, register-interest with a real start date) and eight
clinics spanning US/GB/PL. Pins: only "Enrolling now" studies at a
verifiable US clinic publish, "Up to $X" is a ceiling never a floor,
varies-compensation rows carry no salary keys, and a parseable check-in
date becomes event_start. No live HTTP inside tests.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

STUDIES_FIXTURE = ROOT / "tests" / "fixtures" / "trialmed_studies.json"
CLINICS_FIXTURE = ROOT / "tests" / "fixtures" / "trialmed_clinics.json"


def _studies() -> list:
    return json.loads(STUDIES_FIXTURE.read_text(encoding="utf-8"))


def _clinics() -> list:
    return json.loads(CLINICS_FIXTURE.read_text(encoding="utf-8"))


class TrialmedTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import trialmed as mod
        self.mod = mod

    def _search(self, studies_payload: object, clinics_payload: object = None,
                **kw) -> list[dict]:
        clinics = _clinics() if clinics_payload is None else clinics_payload

        def fake_get_json(url, params=None, **_kw):
            if url == self.mod._CLINICS_URL:
                return clinics
            return studies_payload

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            return self.mod.search_trialmed(**kw)

    def test_row_mapping_from_real_capture(self) -> None:
        rows = self._search(_studies())
        # 5 fixture studies: coming-soon, multi-clinic, register-interest drop
        self.assertEqual(len(rows), 2)
        healthy = next(r for r in rows if "3152225" in r["title"])
        self.assertEqual(healthy["title"], "3152225 AUS Healthy")
        self.assertEqual(healthy["url"], "https://trialmed.com/studies/3152225-aus/")
        self.assertEqual(healthy["date_posted"], "2026-07-10T14:25:11")
        self.assertEqual(healthy["location"], "Austin, TX")
        for row in rows:
            self.assertEqual(row["vertical"], "body")
            self.assertEqual(row["source"], "trialmed")

    def test_only_enrolling_now_studies_publish(self) -> None:
        rows = self._search(_studies())
        titles = " | ".join(r["title"] for r in rows)
        # "Coming soon" (Alzheimer's) and "Register interest now" (MDD) drop
        self.assertNotIn("Alzheimer", titles)
        self.assertNotIn("Depressive", titles)

    def test_us_clinic_gate(self) -> None:
        # GB/PL clinics never enter the US city map; the clinic NAMED
        # "Birmingham" is Birmingham, AL — the UK one is named "Midlands".
        def fake_get_json(url, params=None, **_kw):
            return _clinics()

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            cities = self.mod._fetch_us_cities()
        for uk in ("midlands", "manchester", "warsaw"):
            self.assertNotIn(uk, cities)
        self.assertEqual(cities["birmingham"], "Birmingham, AL")
        self.assertEqual(cities["austin"], "Austin, TX")
        # an enrolling multi-clinic study names no city, so its country
        # can't be verified against the clinic list — it must not publish
        rows = self._search(_studies())
        self.assertNotIn("Afib", " | ".join(r["title"] for r in rows))

    def test_up_to_compensation_is_a_ceiling_never_a_floor(self) -> None:
        rows = self._search(_studies())
        paid = next(r for r in rows if "3152225" in r["title"])
        self.assertEqual(paid["salary_max"], 15800.0)
        self.assertNotIn("salary_min", paid)
        self.assertEqual(paid["salary_source"], "reported")
        self.assertEqual(paid["quest"]["pay_note"], "Up to $15800")
        self.assertIn("Up to $15800", paid["description"])

    def test_varies_compensation_emits_no_salary_keys(self) -> None:
        rows = self._search(_studies())
        varies = next(r for r in rows if "DPN" in r["title"])
        self.assertNotIn("salary_min", varies)
        self.assertNotIn("salary_max", varies)
        self.assertEqual(varies["quest"]["pay_note"], "Compensation varies by study")
        self.assertIn("Compensation varies by study", varies["description"])

    def test_parseable_checkin_becomes_event_start(self) -> None:
        # the fixture's real dated study ("Starts Oct 28th", posted
        # 2025-07-02) is register-interest so it never publishes; the
        # helper is pinned on its real strings directly
        anchor = datetime(2025, 7, 2)
        self.assertEqual(self.mod._parse_start("Starts Oct 28th", anchor),
                         "2025-10-28")
        # yearless dates before the post date roll forward a year
        self.assertEqual(self.mod._parse_start("Starts Jan 5th",
                                               datetime(2025, 11, 20)),
                         "2026-01-05")
        self.assertIsNone(self.mod._parse_start("Flexible start date", anchor))
        self.assertIsNone(self.mod._parse_start("Multiple start dates", anchor))
        for row in self._search(_studies()):
            self.assertNotIn("event_start", row)

    def test_paginates_until_a_short_page(self) -> None:
        calls: list[dict] = []
        page1 = _studies()[:2]
        page2 = _studies()[2:3]

        def fake_get_json(url, params=None, **_kw):
            if url == self.mod._CLINICS_URL:
                return _clinics()
            calls.append(dict(params or {}))
            return page1 if params["page"] == "1" else page2

        with patch.object(self.mod, "_PER_PAGE", 2), \
                patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            self.mod.search_trialmed()
        self.assertEqual([c["page"] for c in calls], ["1", "2"])
        self.assertEqual(calls[0]["per_page"], "2")

    def test_single_page_requests_full_per_page(self) -> None:
        captured: list[dict] = []

        def fake_get_json(url, params=None, **_kw):
            if url == self.mod._CLINICS_URL:
                return _clinics()
            captured.append(dict(params or {}))
            return _studies()

        with patch.object(self.mod, "_get_json", side_effect=fake_get_json):
            self.mod.search_trialmed()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["per_page"], "100")
        self.assertEqual(captured[0]["page"], "1")

    def test_bad_payloads_return_empty(self) -> None:
        for bad in (None, {}, "x", 42):
            self.assertEqual(self._search(bad), [])
        # no clinic list means no US verification, so nothing publishes
        for bad_clinics in ({}, [], "x"):
            self.assertEqual(self._search(_studies(), clinics_payload=bad_clinics), [])


class TrialmedRegistryTest(unittest.TestCase):
    def test_registered_as_body_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.trialmed  # noqa: F401

        reg = get_registry()
        self.assertIn("trialmed", reg)
        meta = reg["trialmed"]
        self.assertEqual(meta.vertical, "body")
        self.assertEqual(meta.display_name, "Trialmed (PPD clinics)")
        self.assertFalse(meta.enabled_by_default)
        self.assertEqual(meta.refresh_hours, 12)
        self.assertTrue(meta.full_snapshot)
        self.assertIsNone(meta.stale_after_days)
        self.assertEqual(meta.allowed_url_hosts, ("trialmed.com",))
        self.assertTrue(callable(meta.search_fn))
        # Quest scrapers never join the default career sweep.
        self.assertNotIn("trialmed", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
