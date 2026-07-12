"""Contract tests for the CallingAllPapers CFP scraper (speak kind).

Fixture is a trimmed REAL response from GET
https://api.callingallpapers.com/v1/cfp (captured live 2026-07-12,
HTTP 200, 295 cfps; 5 kept, meta.count adjusted to the trim): one
sessionize row, one papercall row, one missing-location row (online),
the earliest-deadline row to prove the past-deadline drop, and a real
tinyurl row to prove the shortener reject. The live feed contains no
already-expired rows, so tests freeze the clock between two real
deadlines instead of aging the fixture. No live HTTP inside tests.
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

FIXTURE = ROOT / "tests" / "fixtures" / "callingallpapers_cfp.json"

# after hayaData 2026 closes (07-12), before Terraform Community
# Brazil closes (07-16)
NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


def _load_fixture() -> list:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cfps"]


class CallingAllPapersTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import callingallpapers as mod
        self.mod = mod

    def _search(self, payload: object, now: datetime = NOW, **kw) -> list[dict]:
        with patch.object(self.mod, "_fetch_cfps", return_value=payload), \
             patch.object(self.mod, "_utcnow", return_value=now):
            return self.mod.search_callingallpapers(**kw)

    def test_row_mapping_from_real_capture(self) -> None:
        rows = self._search(_load_fixture())
        # 5 fixture cfps: the past-deadline, tinyurl, and papercall rows
        # drop (papercall-direct owns papercall.io supply)
        self.assertEqual(len(rows), 2)
        devfest = next(r for r in rows if r["company"] == "Devfest Milano 2026")
        self.assertEqual(devfest["title"], "Speak at Devfest Milano 2026")
        self.assertEqual(devfest["url"], "https://sessionize.com/devfest-milano-2026")
        self.assertEqual(devfest["source"], "callingallpapers")
        self.assertEqual(devfest["vertical"], "speak")
        self.assertEqual(devfest["location"], "Milan, Italy")
        self.assertFalse(devfest["is_remote"])
        self.assertEqual(devfest["quest"]["apply_by"], "2026-07-30T21:59:00+00:00")
        self.assertEqual(devfest["event_start"], "2026-10-09T22:00:00+00:00")
        self.assertEqual(devfest["event_end"], "2026-10-09T22:00:00+00:00")
        self.assertEqual(devfest["date_posted"], "2026-06-09T03:05:57+00:00")

    def test_papercall_rows_belong_to_the_papercall_scraper(self) -> None:
        # the same CFP appears on papercall.io under two different URLs
        # (slug page there, deep submission link here), so URL dedupe
        # cannot catch the overlap; the partition can. CAP keeps
        # sessionize and one-off hosts, papercall-direct owns its own.
        rows = self._search(_load_fixture())
        self.assertFalse(any("papercall.io" in r["url"] for r in rows))
        self.assertFalse(any(r["company"] == "HoneyCON26" for r in rows))

    def test_missing_location_means_online(self) -> None:
        rows = self._search(_load_fixture())
        terraform = next(
            r for r in rows if r["company"] == "Terraform Community Brazil"
        )
        self.assertEqual(terraform["location"], "Online")
        self.assertTrue(terraform["is_remote"])

    def test_past_deadline_rows_dropped(self) -> None:
        names = [r["company"] for r in self._search(_load_fixture())]
        self.assertNotIn("hayaData 2026", names)
        # same fixture before that deadline: the row publishes, proving
        # the drop is deadline-driven, not name-driven
        earlier = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
        names = [r["company"] for r in self._search(_load_fixture(), now=earlier)]
        self.assertIn("hayaData 2026", names)

    def test_shortener_and_non_https_uris_rejected(self) -> None:
        names = [r["company"] for r in self._search(_load_fixture())]
        self.assertNotIn("ASF Community Over Code / ChurConf", names)
        # synthetic scheme edge: a real row downgraded to http must drop
        row = dict(_load_fixture()[0])
        row["uri"] = row["uri"].replace("https://", "http://")
        self.assertEqual(self._search([row]), [])

    def test_no_salary_keys_ever(self) -> None:
        for row in self._search(_load_fixture()):
            salary_keys = [k for k in row if k.startswith("salary")]
            self.assertEqual(salary_keys, [])

    def test_max_results_caps_rows(self) -> None:
        rows = self._search(_load_fixture(), max_results=1)
        self.assertEqual(len(rows), 1)

    def test_bad_payloads_return_empty(self) -> None:
        for bad in ([], [None, "x", 42], [{"name": "", "uri": ""}]):
            self.assertEqual(self._search(bad), [])

    def test_fetch_unwraps_envelope_and_survives_garbage(self) -> None:
        class _Resp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                pass

            def json(self):
                return self._payload

        with patch.object(self.mod.requests, "get", return_value=_Resp({"cfps": [{"name": "x"}], "meta": {"count": 1}})):
            self.assertEqual(self.mod._fetch_cfps(), [{"name": "x"}])
        for garbage in ({"cfps": "nope"}, "nope", 42, None):
            with patch.object(self.mod.requests, "get", return_value=_Resp(garbage)):
                self.assertEqual(self.mod._fetch_cfps(), [])


class CallingAllPapersRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        from job_finder.tools.scrapers import callingallpapers  # noqa: F401  (registers)
        from job_finder.tools.scrapers._registry import (
            default_scraper_names,
            get_registry,
        )
        meta = get_registry()["callingallpapers"]
        self.assertEqual(meta.display_name, "CallingAllPapers")
        self.assertEqual(meta.vertical, "speak")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertTrue(meta.full_snapshot)
        # uris span sessionize/papercall/one-off conference hosts by design;
        # the scraper's own https + shortener gate stands in for a host gate
        self.assertIsNone(meta.allowed_url_hosts)
        self.assertFalse(meta.enabled_by_default)
        # quest source: never part of the default career sweep
        self.assertNotIn("callingallpapers", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
