"""Contract tests for the Consider board scraper (a16z crypto + VC networks).

Consider powers VC talent-network job boards (a16z crypto's portfolio board at
a16zcrypto.com/jobs) by server-rendering every listing into the page inside a
``const portfolioJobs = [...]`` array, grouped by company. These tests pin the
HTML extractor, the flatten/normalize shape, salary annualization, the role
filter (incl. crypto rescue), dedup/cap, and graceful degradation so the
scraper doesn't silently break when the page shifts.
"""

from __future__ import annotations

import json
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
    """A Consider board job object shaped like the real live payload."""
    base = {
        "companyName": "The Better Money Company",
        "companyDomain": "bettermoney.com",
        "title": "Security Engineer",
        "url": "https://jobs.ashbyhq.com/bettermoney/0ca69371-b918-450d-8c42-0f44abba8cf7",
        "locations": ["New York City, New York, United States", "New York City"],
        "remote": False,
        "salary": {"currency": "USD", "minValue": 175000, "maxValue": 225000, "period": "Year"},
        "seniorities": ["Mid"],
        "functions": ["Engineering"],
        "skills": ["Application Security", "Terraform", "SOC 2"],
        "createdAt": "2026-06-05T23:57:04Z",
        "isFeatured": False,
        "yearsExperience": {"max": None, "min": 5},
    }
    base.update(overrides)
    return base


def _html(groups: list[dict], *, anchor: bool = True) -> str:
    """Wrap company-grouped jobs in a minimal board page around the array."""
    blob = json.dumps(groups)
    inner = f"const portfolioJobs = {blob};" if anchor else f"const somethingElse = {blob};"
    return (
        "<!doctype html><html><head><title>Jobs</title></head><body>"
        "<div id='root'></div>"
        f"<script>(function(){{{inner}window.__PORTFOLIO_JOBS_DATA__ = portfolioJobs;}})();</script>"
        "</body></html>"
    )


def _group(company: str, jobs: list[dict]) -> dict:
    return {"company": company, "jobs": jobs}


class ConsiderExtractTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import consider as mod
        self.mod = mod

    def test_extract_pulls_the_array(self) -> None:
        groups = [_group("Acme", [_job()])]
        out = self.mod._extract_portfolio_jobs(_html(groups))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["company"], "Acme")
        self.assertEqual(len(out[0]["jobs"]), 1)

    def test_extract_handles_brackets_inside_strings(self) -> None:
        # A skill containing brackets/quotes must not confuse the scanner.
        tricky = _job(skills=["C[++]", 'says "hi"', "a]b[c"])
        out = self.mod._extract_portfolio_jobs(_html([_group("Acme", [tricky])]))
        self.assertEqual(out[0]["jobs"][0]["skills"], ["C[++]", 'says "hi"', "a]b[c"])

    def test_extract_missing_anchor_returns_empty(self) -> None:
        self.assertEqual(self.mod._extract_portfolio_jobs(_html([], anchor=False)), [])

    def test_extract_garbage_returns_empty(self) -> None:
        self.assertEqual(self.mod._extract_portfolio_jobs("<html>no jobs here</html>"), [])

    def test_iter_jobs_flattens_groups(self) -> None:
        groups = [
            _group("Acme", [_job(title="A"), _job(title="B")]),
            _group("Beta", [_job(title="C")]),
            {"company": "NoJobs"},  # malformed group, skipped
        ]
        pairs = list(self.mod._iter_jobs(groups))
        self.assertEqual([p[0]["title"] for p in pairs], ["A", "B", "C"])
        self.assertEqual(pairs[0][1], "Acme")
        self.assertEqual(pairs[2][1], "Beta")


class ConsiderNormalizeTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import consider as mod
        self.mod = mod

    def test_normalize_maps_fields_correctly(self) -> None:
        out = self.mod._normalize_job(_job(), "The Better Money Company")
        self.assertEqual(out["title"], "Security Engineer")
        self.assertEqual(out["company"], "The Better Money Company")
        self.assertEqual(out["source"], "consider")
        self.assertFalse(out["is_remote"])
        # Longest (most specific) location string wins.
        self.assertEqual(out["location"], "New York City, New York, United States")
        self.assertEqual(out["salary_min"], 175000.0)
        self.assertEqual(out["salary_max"], 225000.0)
        self.assertIn("Application Security", out["description"])
        self.assertIn("Engineering", out["description"])
        self.assertEqual(out["date_posted"], "2026-06-05T23:57:04Z")
        self.assertTrue(out["remote_flag_reported"])
        self.assertTrue(out["crypto"])  # crypto board → flagged

    def test_normalize_has_all_contract_keys(self) -> None:
        out = self.mod._normalize_job(_job(), "Acme")
        for key in (
            "title", "company", "location", "url", "source", "description",
            "salary_min", "salary_max", "date_posted", "is_remote", "company_size",
        ):
            self.assertIn(key, out)

    def test_normalize_falls_back_to_group_company(self) -> None:
        out = self.mod._normalize_job(_job(companyName=None), "Group Co")
        self.assertEqual(out["company"], "Group Co")

    def test_normalize_remote_with_no_location(self) -> None:
        out = self.mod._normalize_job(_job(remote=True, locations=[]), "Acme")
        self.assertTrue(out["is_remote"])
        self.assertEqual(out["location"], "Remote")

    def test_normalize_on_site_with_no_location(self) -> None:
        out = self.mod._normalize_job(_job(remote=False, locations=[]), "Acme")
        self.assertEqual(out["location"], "Not specified")

    def test_normalize_missing_salary(self) -> None:
        out = self.mod._normalize_job(_job(salary=None), "Acme")
        self.assertIsNone(out["salary_min"])
        self.assertIsNone(out["salary_max"])

    def test_normalize_hourly_salary_annualized(self) -> None:
        out = self.mod._normalize_job(
            _job(salary={"currency": "USD", "minValue": 50, "maxValue": 75, "period": "Hour"}),
            "Acme",
        )
        self.assertEqual(out["salary_min"], 50 * 2080)
        self.assertEqual(out["salary_max"], 75 * 2080)

    def test_normalize_non_crypto_board_omits_flag(self) -> None:
        out = self.mod._normalize_job(_job(), "Acme", is_crypto=False)
        self.assertNotIn("crypto", out)


class ConsiderSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import consider as mod
        self.mod = mod

    def _patched_html(self, groups: list[dict]):
        return patch.object(self.mod, "_fetch_board_html", return_value=_html(groups))

    def test_returns_parsed_job_dicts(self) -> None:
        with self._patched_html([_group("Acme", [_job()])]):
            jobs = self.mod.search_consider(roles=None, max_results=10)
        self.assertTrue(jobs)
        self.assertEqual(jobs[0]["source"], "consider")
        self.assertEqual(jobs[0]["title"], "Security Engineer")

    def test_role_filter_keeps_match_drops_non_match(self) -> None:
        groups = [_group("Acme", [
            _job(title="Backend Engineer", url="https://x/eng"),
            _job(title="Office Manager", url="https://x/office", skills=[], seniorities=[], functions=[]),
        ])]
        with self._patched_html(groups):
            jobs = self.mod.search_consider(roles=["backend engineer"], max_results=10)
        titles = [j["title"] for j in jobs]
        self.assertIn("Backend Engineer", titles)
        self.assertNotIn("Office Manager", titles)

    def test_crypto_title_passes_role_filter(self) -> None:
        """A crypto-flavoured title passes via _match_roles_crypto even when it
        doesn't word-match the user's normal roles (crypto board)."""
        groups = [_group("Acme", [
            _job(title="Solidity Engineer", url="https://x/sol", skills=[], seniorities=[], functions=[]),
        ])]
        with self._patched_html(groups):
            jobs = self.mod.search_consider(roles=["data engineer"], max_results=10)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "Solidity Engineer")

    def test_respects_max_results(self) -> None:
        many = [_job(title="Backend Engineer", url=f"https://x/{i}") for i in range(20)]
        with self._patched_html([_group("Acme", many)]):
            jobs = self.mod.search_consider(roles=None, max_results=5)
        self.assertEqual(len(jobs), 5)

    def test_dedups_repeated_urls(self) -> None:
        dupes = [
            _job(url="https://x/same", title="Backend Engineer"),
            _job(url="https://x/same", title="Other Engineer"),
        ]
        with self._patched_html([_group("Acme", dupes)]):
            jobs = self.mod.search_consider(roles=None, max_results=10)
        urls = [j["url"] for j in jobs]
        self.assertEqual(len(urls), len(set(urls)))

    def test_empty_html_returns_empty(self) -> None:
        with patch.object(self.mod, "_fetch_board_html", return_value=""):
            jobs = self.mod.search_consider(roles=["engineer"], max_results=10)
        self.assertEqual(jobs, [])

    def test_network_error_returns_empty_not_exception(self) -> None:
        with patch.object(self.mod.requests, "get", side_effect=requests.RequestException("boom")):
            jobs = self.mod.search_consider(roles=["engineer"], max_results=10)
        self.assertEqual(jobs, [])

    def test_fetch_board_html_returns_empty_on_non_200(self) -> None:
        resp = MagicMock()
        resp.status_code = 503
        with patch.object(self.mod.requests, "get", return_value=resp):
            out = self.mod._fetch_board_html("https://a16zcrypto.com/jobs/")
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
