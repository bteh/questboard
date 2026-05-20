"""Contract tests for CryptoJobsList ``__NEXT_DATA__`` parser.

CryptoJobsList migrated off their public JSON API + RSS feed in spring 2026
— both now return 403. Their Next.js site embeds the job list in a
``__NEXT_DATA__`` script tag at ``props.pageProps.jobs``. These tests pin
the parser shape so the scraper doesn't silently break again when the
schema shifts.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


def _make_html(jobs: list[dict]) -> str:
    """Wrap a synthetic jobs list in the __NEXT_DATA__ envelope."""
    payload = {
        "props": {"pageProps": {"jobs": jobs}},
        "page": "/",
    }
    return (
        '<!doctype html><html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></body></html>"
    )


_SAMPLE_JOB = {
    "_id": {"$oid": "abc"},
    "jobTitle": "Senior Solidity Engineer",
    "companyName": "Re7 Labs",
    "jobLocation": "",
    "tags": ["full-time", "remote", "defi", "solidity"],
    "remote": True,
    "companySlug": "re7-labs",
    "seoSlug": "senior-solidity-engineer-at-re7-labs",
    "publishedAt": "2026-04-29T10:27:55.944Z",
    "salaryString": None,
    "jobPostingJSONLD": json.dumps({
        "@graph": [{
            "@type": "JobPosting",
            "baseSalary": {
                "@type": "MonetaryAmount",
                "currency": "USD",
                "value": {"minValue": 150000, "maxValue": 230000},
            },
        }],
    }),
}


class CryptoJobsListParserTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import cryptojobslist as mod
        self.mod = mod

    def test_extracts_jobs_from_next_data(self) -> None:
        html = _make_html([_SAMPLE_JOB])
        parsed = self.mod._extract_next_data_jobs(html)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["jobTitle"], "Senior Solidity Engineer")

    def test_returns_empty_when_no_next_data(self) -> None:
        self.assertEqual(self.mod._extract_next_data_jobs("<html></html>"), [])
        self.assertEqual(self.mod._extract_next_data_jobs(""), [])

    def test_returns_empty_when_next_data_has_no_jobs(self) -> None:
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"foo":"bar"}}}'
            "</script>"
        )
        self.assertEqual(self.mod._extract_next_data_jobs(html), [])

    def test_normalize_maps_fields_correctly(self) -> None:
        out = self.mod._normalize_next_job(_SAMPLE_JOB)
        self.assertEqual(out["title"], "Senior Solidity Engineer")
        self.assertEqual(out["company"], "Re7 Labs")
        self.assertEqual(out["url"], "https://cryptojobslist.com/jobs/senior-solidity-engineer-at-re7-labs")
        self.assertTrue(out["is_remote"])
        self.assertEqual(out["location"], "Remote")
        self.assertEqual(out["source"], "cryptojobslist")
        self.assertEqual(out["salary_min"], 150000)
        self.assertEqual(out["salary_max"], 230000)

    def test_normalize_handles_missing_jsonld_gracefully(self) -> None:
        job = dict(_SAMPLE_JOB, jobPostingJSONLD=None)
        out = self.mod._normalize_next_job(job)
        self.assertIsNone(out["salary_min"])
        self.assertIsNone(out["salary_max"])

    def test_normalize_handles_non_remote_with_location(self) -> None:
        job = dict(
            _SAMPLE_JOB,
            jobLocation="New York, NY",
            remote=False,
            tags=["full-time", "engineering"],
        )
        out = self.mod._normalize_next_job(job)
        self.assertFalse(out["is_remote"])
        self.assertEqual(out["location"], "New York, NY")

    def test_search_filters_by_role(self) -> None:
        html = _make_html([
            _SAMPLE_JOB,
            dict(_SAMPLE_JOB,
                 jobTitle="Marketing Coordinator",
                 seoSlug="marketing-at-x",
                 jobPostingJSONLD=None),
        ])
        with patch.object(self.mod, "_fetch_html", return_value=html):
            jobs = self.mod.search_cryptojobslist(roles=["solidity engineer"], max_results=10)
        titles = [j["title"] for j in jobs]
        self.assertIn("Senior Solidity Engineer", titles)
        self.assertNotIn("Marketing Coordinator", titles)

    def test_search_passes_crypto_terms_through_role_filter(self) -> None:
        """Crypto-flavored titles bypass strict role matching via _match_roles_crypto."""
        html = _make_html([
            dict(_SAMPLE_JOB,
                 jobTitle="ZK Circuit Researcher",
                 seoSlug="zk-research",
                 jobPostingJSONLD=None),
        ])
        with patch.object(self.mod, "_fetch_html", return_value=html):
            # role doesn't word-match, but "zk" is a crypto keyword → passes
            jobs = self.mod.search_cryptojobslist(roles=["data engineer"], max_results=10)
        self.assertEqual(len(jobs), 1)

    def test_search_paginates_until_max_results(self) -> None:
        """When page 1 doesn't fill max_results, the scraper fetches page 2."""
        page1 = _make_html([dict(_SAMPLE_JOB, seoSlug=f"job-{i}") for i in range(25)])
        page2 = _make_html([dict(_SAMPLE_JOB, seoSlug=f"job-{i+25}") for i in range(25)])
        fetch_mock = MagicMock(side_effect=[page1, page2, ""])
        with patch.object(self.mod, "_fetch_html", fetch_mock):
            jobs = self.mod.search_cryptojobslist(roles=None, max_results=40)
        self.assertGreaterEqual(len(jobs), 40)
        self.assertLessEqual(fetch_mock.call_count, 4)

    def test_search_returns_empty_on_403(self) -> None:
        """If Cloudflare ever locks down the homepage too, degrade gracefully."""
        with patch.object(self.mod, "_fetch_html", return_value=""):
            jobs = self.mod.search_cryptojobslist(roles=["engineer"], max_results=10)
        self.assertEqual(jobs, [])


if __name__ == "__main__":
    unittest.main()
