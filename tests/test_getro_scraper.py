"""Contract tests for the Getro board-search scraper.

Getro powers crypto-fund / VC talent-network job boards. Jobs are fetched
through a free POST endpoint and arrive at ``results.jobs[]`` with structured
fields (title, organization.name, url, work_mode, locations, seniority,
skills, compensation_*_cents). These tests pin the parser/normalizer shape and
the role-filter + network-error behaviour so the scraper degrades gracefully
and doesn't silently break when the schema shifts.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


def _job(**overrides) -> dict:
    """A Getro search-job object shaped like the real live response."""
    base = {
        "id": 84696367,
        "title": "Senior Backend Engineer",
        "slug": "84696367-senior-backend-engineer",
        "url": "https://jobs.ashbyhq.com/halliday/abc-123",
        "source": "career_page",
        "work_mode": "remote",
        "locations": ["United States", "Remote"],
        "searchable_locations": ["United States", "North America"],
        "seniority": "senior",
        "skills": ["Go", "Kubernetes", "Solidity"],
        "has_description": True,
        "created_at": 1782835728,
        "compensation_public": True,
        "compensation_amount_min_cents": 18500000,
        "compensation_amount_max_cents": 22000000,
        "compensation_currency": "USD",
        "compensation_period": "year",
        "compensation_offers_equity": None,
        "organization": {
            "id": 1394558,
            "name": "Halliday",
            "slug": "halliday-2",
            "head_count": 42,
            "stage": "series_a",
            "industry_tags": ["Blockchain", "Web3"],
            "logo_url": "https://cdn.getro.com/x.png",
            "topics": [],
        },
    }
    base.update(overrides)
    return base


def _payload(jobs: list[dict], count: int | None = None) -> dict:
    """Wrap jobs in the real ``{"results": {"jobs": [...], "count": N}}`` envelope."""
    return {"results": {"jobs": jobs, "count": count if count is not None else len(jobs)}}


class GetroNormalizeTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import getro as mod
        self.mod = mod

    def test_normalize_maps_fields_correctly(self) -> None:
        out = self.mod._normalize_job(_job())
        self.assertEqual(out["title"], "Senior Backend Engineer")
        self.assertEqual(out["company"], "Halliday")
        self.assertEqual(out["url"], "https://jobs.ashbyhq.com/halliday/abc-123")
        self.assertEqual(out["source"], "getro")
        self.assertTrue(out["is_remote"])
        self.assertEqual(out["location"], "United States, Remote")
        self.assertEqual(out["company_size"], "42")
        # cents -> whole dollars
        self.assertEqual(out["salary_min"], 185000.0)
        self.assertEqual(out["salary_max"], 220000.0)
        self.assertIn("Solidity", out["description"])
        self.assertIn("senior", out["description"].lower())

    def test_normalize_has_all_contract_keys(self) -> None:
        out = self.mod._normalize_job(_job())
        for key in (
            "title", "company", "location", "url", "source", "description",
            "salary_min", "salary_max", "date_posted", "is_remote", "company_size",
        ):
            self.assertIn(key, out)
        self.assertLessEqual(len(out["description"]), 3000)

    def test_normalize_handles_on_site_and_missing_comp(self) -> None:
        out = self.mod._normalize_job(_job(
            work_mode="on_site",
            locations=["New York, NY, USA"],
            compensation_amount_min_cents=None,
            compensation_amount_max_cents=None,
        ))
        self.assertFalse(out["is_remote"])
        self.assertEqual(out["location"], "New York, NY, USA")
        self.assertIsNone(out["salary_min"])
        self.assertIsNone(out["salary_max"])

    def test_normalize_handles_empty_locations(self) -> None:
        out = self.mod._normalize_job(_job(work_mode="on_site", locations=[]))
        self.assertEqual(out["location"], "Not specified")
        out_remote = self.mod._normalize_job(_job(work_mode="remote", locations=[]))
        self.assertEqual(out_remote["location"], "Remote")


class GetroSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import getro as mod
        self.mod = mod

    def test_returns_parsed_job_dicts(self) -> None:
        # One short page per network -> stops after page 0 for each.
        with patch.object(self.mod, "_fetch_search", return_value=[_job()]):
            jobs = self.mod.search_getro(roles=None, max_results=10)
        self.assertTrue(jobs)
        first = jobs[0]
        self.assertEqual(first["source"], "getro")
        self.assertEqual(first["company"], "Halliday")
        self.assertEqual(first["title"], "Senior Backend Engineer")

    def test_role_filter_keeps_match_drops_non_match(self) -> None:
        page = [
            _job(title="Senior Backend Engineer", url="https://x/eng"),
            _job(title="Office Manager", url="https://x/office",
                 skills=[], seniority=None),
        ]
        with patch.object(self.mod, "_fetch_search", return_value=page):
            jobs = self.mod.search_getro(roles=["backend engineer"], max_results=10)
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Backend Engineer", titles)
        self.assertNotIn("Office Manager", titles)

    def test_crypto_title_passes_role_filter(self) -> None:
        """A crypto-flavoured title passes via _match_roles_crypto even when it
        doesn't word-match the user's normal roles."""
        page = [_job(title="Solidity Engineer", url="https://x/sol", skills=[])]
        with patch.object(self.mod, "_fetch_search", return_value=page):
            jobs = self.mod.search_getro(roles=["data engineer"], max_results=10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Solidity Engineer")

    def test_respects_max_results(self) -> None:
        full_page = [_job(title="Backend Engineer", url=f"https://x/{i}") for i in range(20)]
        # Always return a full page so pagination would continue if uncapped.
        with patch.object(self.mod, "_fetch_search", return_value=full_page):
            jobs = self.mod.search_getro(roles=None, max_results=5)
        self.assertEqual(len(jobs), 5)

    def test_dedups_repeated_urls(self) -> None:
        dupe = [_job(url="https://x/same"), _job(url="https://x/same", title="Other Engineer")]
        with patch.object(self.mod, "_fetch_search", return_value=dupe):
            jobs = self.mod.search_getro(roles=None, max_results=10)
        urls = [j["url"] for j in jobs]
        self.assertEqual(len(urls), len(set(urls)))

    def test_network_error_returns_empty_not_exception(self) -> None:
        """A network failure during fetch must degrade to [] — never raise."""
        def boom(network_id, page):
            raise requests.RequestException("connection reset")

        # Patch requests.post inside the module so the real try/except runs.
        with patch.object(self.mod.requests, "post", side_effect=requests.RequestException("boom")):
            jobs = self.mod.search_getro(roles=["engineer"], max_results=10)
        self.assertEqual(jobs, [])

    def test_fetch_search_returns_empty_on_non_200(self) -> None:
        resp = MagicMock()
        resp.status_code = 503
        with patch.object(self.mod.requests, "post", return_value=resp):
            out = self.mod._fetch_search(1625, 0)
        self.assertEqual(out, [])

    def test_fetch_search_parses_results_jobs(self) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = _payload([_job()])
        with patch.object(self.mod.requests, "post", return_value=resp):
            out = self.mod._fetch_search(1625, 0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Senior Backend Engineer")


if __name__ == "__main__":
    unittest.main()
