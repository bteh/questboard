"""Contract tests for the Care.com sitemap scraper (lookafter kind).

Fixtures are trimmed REAL captures from 2026-07-10: carecom_sitemap.xml
is a seven-entry slice of alpha-omega-jobs_manual_1.xml.gz covering all
five job verticals, and carecom_job.html keeps a real /job/ page's
JSON-LD blocks (JobPosting plus the BreadcrumbList decoy) inside a
minimal shell. Pins: sitemap ids sort newest-first with seniorcare and
housekeeping filtered out, the family's own posted hourly range maps to
structured figures, the poster is credited (the platform never stands
in as counterparty), validThrough becomes apply_by and expired rows
drop. The clock is frozen via _utcnow so the fixture's validThrough
stays stable. No live HTTP inside tests.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

JOB_FIXTURE = ROOT / "tests" / "fixtures" / "carecom_job.html"
SITEMAP_FIXTURE = ROOT / "tests" / "fixtures" / "carecom_sitemap.xml"

# The capture date; the fixture's validThrough (2026-08-25) is still live.
FROZEN_NOW = datetime(2026, 7, 10, tzinfo=timezone.utc)

JOB_URL = "https://www.care.com/job/childcare/pa/irwin/33852898-part-time-nanny-position-for-baby"


class CarecomSitemapTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import carecom as mod
        self.mod = mod
        self.urls = mod._LOC_RE.findall(SITEMAP_FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_covers_all_five_verticals(self) -> None:
        self.assertEqual(len(self.urls), 7)
        for vertical in ("childcare", "petcare", "specialneeds", "seniorcare", "housekeeping"):
            self.assertTrue(any(f"/job/{vertical}/" in u for u in self.urls))

    def test_round_robins_verticals_pets_first(self) -> None:
        # kept verticals only, round-robined with pets leading so high-volume
        # childcare can't crowd pet-care out of the fetch cap; newest-first
        # within each vertical.
        ordered = self.mod._newest_first(self.urls)
        self.assertEqual(len(ordered), 5)
        for url in ordered:
            self.assertNotIn("/job/seniorcare/", url)
            self.assertNotIn("/job/housekeeping/", url)
        matches = [self.mod._JOB_URL_RE.match(u) for u in ordered]
        verts = [m.group(1) for m in matches]
        ids = [int(m.group(2)) for m in matches]
        self.assertEqual(verts[0], "petcare")     # pets lead the round-robin
        self.assertEqual(ids[0], 35318774)         # highest petcare id, first slot
        self.assertIn(34839620, ids)               # nothing kept is dropped
        for v in set(verts):                       # newest-first within each vertical
            v_ids = [i for i, vv in zip(ids, verts) if vv == v]
            self.assertEqual(v_ids, sorted(v_ids, reverse=True))

    def test_duplicate_ids_dedupe(self) -> None:
        self.assertEqual(
            self.mod._newest_first(self.urls + self.urls),
            self.mod._newest_first(self.urls),
        )

    def test_gz_sitemap_payload_is_gunzipped(self) -> None:
        import gzip

        payload = gzip.compress(SITEMAP_FIXTURE.read_bytes())

        class _Resp:
            content = payload
            def raise_for_status(self) -> None:
                return None

        with patch.object(self.mod.requests, "get", return_value=_Resp()):
            text = self.mod._fetch_text(
                "https://www.care.com/alpha-omega-jobs_manual_1.xml.gz",
                self.mod._XML_ACCEPT, 15,
            )
        self.assertEqual(len(self.mod._LOC_RE.findall(text)), 7)


class CarecomRowTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import carecom as mod
        self.mod = mod
        self.html = JOB_FIXTURE.read_text(encoding="utf-8")

    def _search(self, urls=None, page=None, now=FROZEN_NOW, **kw) -> list[dict]:
        urls = [JOB_URL] if urls is None else list(urls)
        with patch.object(self.mod, "_fetch_job_urls", return_value=urls), \
             patch.object(self.mod, "_fetch_text", return_value=page or self.html) as fetch, \
             patch.object(self.mod.time, "sleep"), \
             patch.object(self.mod, "_utcnow", return_value=now):
            rows = self.mod.search_carecom(**kw)
        self.fetch_calls = fetch.call_count
        return rows

    def test_maps_jsonld_to_lookafter_row(self) -> None:
        rows = self._search()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Part Time Nanny Position For Baby")
        self.assertEqual(row["company"], "Becca B via Care.com")
        self.assertEqual(row["location"], "Irwin, PA")
        self.assertEqual(row["url"], JOB_URL)
        self.assertEqual(row["source"], "carecom")
        self.assertEqual(row["vertical"], "lookafter")
        self.assertEqual(row["date_posted"], "2025-09-16")
        self.assertIn("Proven experience as a nanny", row["description"])
        self.assertNotIn("<h4>", row["description"])

    def test_posted_rate_maps_to_hourly_figures(self) -> None:
        row = self._search()[0]
        self.assertEqual(row["salary_min"], 14.0)
        self.assertEqual(row["salary_max"], 19.0)
        self.assertEqual(row["salary_period"], "hourly")
        self.assertEqual(row["salary_source"], "reported")

    def test_valid_through_becomes_apply_by(self) -> None:
        row = self._search()[0]
        self.assertEqual(row["quest"], {"apply_by": "2026-08-25"})

    def test_expired_valid_through_drops_row(self) -> None:
        past_deadline = datetime(2026, 9, 1, tzinfo=timezone.utc)
        self.assertEqual(self._search(now=past_deadline), [])

    def test_zero_or_absent_basesalary_emits_no_salary_keys(self) -> None:
        posting = self.mod._find_job_posting(self.html)
        salary_keys = {"salary_min", "salary_max", "salary_period", "salary_source"}

        absent = dict(posting)
        del absent["baseSalary"]
        row = self.mod._normalize_posting(absent, JOB_URL)
        self.assertFalse(salary_keys & set(row))

        zeroed = dict(posting)
        zeroed["baseSalary"] = {
            "@type": "MonetaryAmount",
            "currency": "USD",
            "value": {
                "@type": "QuantitativeValue",
                "minValue": "0.00", "maxValue": "0.00", "value": "0.00",
                "unitText": "HOUR",
            },
        }
        row = self.mod._normalize_posting(zeroed, JOB_URL)
        self.assertFalse(salary_keys & set(row))

    def test_max_results_caps_rows_and_detail_fetches(self) -> None:
        urls = self.mod._newest_first(
            self.mod._LOC_RE.findall(SITEMAP_FIXTURE.read_text(encoding="utf-8"))
        )
        rows = self._search(urls=urls, max_results=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.fetch_calls, 2)

    def test_page_without_jobposting_yields_nothing(self) -> None:
        self.assertEqual(self._search(page="<html><body>not a job</body></html>"), [])

    def test_empty_sitemaps_return_empty(self) -> None:
        self.assertEqual(self._search(urls=[]), [])

    def test_failed_detail_fetches_return_empty(self) -> None:
        with patch.object(self.mod, "_fetch_job_urls", return_value=[JOB_URL]), \
             patch.object(self.mod, "_fetch_text", return_value=None), \
             patch.object(self.mod.time, "sleep"):
            self.assertEqual(self.mod.search_carecom(), [])


class CarecomRegistryTest(unittest.TestCase):
    def test_registration_contract(self) -> None:
        from job_finder.tools.scrapers import carecom  # noqa: F401  (registers)
        from job_finder.tools.scrapers._registry import (
            default_scraper_names,
            get_registry,
        )
        meta = get_registry()["carecom"]
        self.assertEqual(meta.display_name, "Care.com")
        self.assertEqual(meta.vertical, "lookafter")
        self.assertEqual(meta.refresh_hours, 24)
        self.assertEqual(meta.stale_after_days, 10)
        self.assertEqual(meta.allowed_url_hosts, ("care.com",))
        self.assertFalse(meta.enabled_by_default)
        # quest source: never part of the default career sweep
        self.assertNotIn("carecom", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
