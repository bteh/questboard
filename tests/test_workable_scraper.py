"""Contract tests for the Workable board scraper.

Workable hosts thousands of company boards at apply.workable.com/<slug>. The
public widget endpoint returns every open posting for an account *with the
full HTML description inline*. These tests pin the payload parse, the
city/country/remote location assembly, the role filter (incl. crypto rescue),
HTML stripping, the fan-out/cap in search_workable, graceful degradation on a
bad payload, and registry registration — so the scraper doesn't silently break
when the widget shape shifts.
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


def _job(**overrides) -> dict:
    """A Workable widget job object shaped like the real live payload."""
    base = {
        "title": "Senior Data Engineer",
        "url": "https://apply.workable.com/j/97904BAC90",
        "shortlink": "https://apply.workable.com/j/97904BAC90",
        "application_url": "https://apply.workable.com/j/97904BAC90/apply",
        "department": "Engineering",
        "employment_type": "Full-time",
        "created_at": "2026-05-29",
        "published_on": "2026-06-01",
        "country": "United States",
        "city": "San Francisco",
        "state": "California",
        "telecommuting": False,
        "description": "<p>We need a <strong>data engineer</strong> with dbt.</p>",
        "code": "ABC",
        "shortcode": "97904BAC90",
    }
    base.update(overrides)
    return base


def _account(name: str = "Hugging Face", jobs: list[dict] | None = None) -> dict:
    return {"name": name, "description": "Company blurb", "jobs": list(jobs or [])}


class WorkableLocationTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import workable as mod
        self.mod = mod

    def test_city_country(self) -> None:
        loc = self.mod._build_location(_job(city="Berlin", country="Germany", telecommuting=False))
        self.assertEqual(loc, "Berlin, Germany")

    def test_remote_with_place(self) -> None:
        loc = self.mod._build_location(_job(city="Paris", country="France", telecommuting=True))
        self.assertIn("Paris, France", loc)
        self.assertIn("Remote", loc)

    def test_remote_only(self) -> None:
        loc = self.mod._build_location(_job(city="", country="", telecommuting=True))
        self.assertEqual(loc, "Remote")

    def test_empty(self) -> None:
        loc = self.mod._build_location(_job(city="", country="", telecommuting=False))
        self.assertEqual(loc, "")

    def test_country_only(self) -> None:
        loc = self.mod._build_location(_job(city="", country="Canada", telecommuting=False))
        self.assertEqual(loc, "Canada")


class WorkableParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import workable as mod
        self.mod = mod

    def _fetch(self, account: dict, roles=None, **kw) -> list[dict]:
        with patch.object(self.mod, "_get_json", return_value=account):
            return self.mod._fetch_company_jobs("acme", roles, **kw)

    def test_parses_a_matching_job(self) -> None:
        jobs = self._fetch(_account(jobs=[_job()]), roles=["data engineer"])
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j["title"], "Senior Data Engineer")
        self.assertEqual(j["company"], "Hugging Face")   # from account .name
        self.assertEqual(j["source"], "workable")
        self.assertEqual(j["url"], "https://apply.workable.com/j/97904BAC90")
        self.assertEqual(j["location"], "San Francisco, United States")

    def test_description_html_is_stripped(self) -> None:
        jobs = self._fetch(_account(jobs=[_job()]), roles=["data engineer"])
        desc = jobs[0]["description"]
        self.assertIn("data engineer", desc)
        self.assertIn("dbt", desc)
        self.assertNotIn("<strong>", desc)
        self.assertNotIn("<p>", desc)

    def test_uses_published_on_as_date(self) -> None:
        jobs = self._fetch(_account(jobs=[_job()]), roles=["data engineer"])
        self.assertEqual(jobs[0]["date_posted"], "2026-06-01")

    def test_falls_back_to_created_at_when_unpublished(self) -> None:
        jobs = self._fetch(_account(jobs=[_job(published_on=None)]), roles=["data engineer"])
        self.assertEqual(jobs[0]["date_posted"], "2026-05-29")

    def test_remote_flag_from_telecommuting(self) -> None:
        jobs = self._fetch(_account(jobs=[_job(telecommuting=True)]), roles=["data engineer"])
        self.assertTrue(jobs[0]["is_remote"])

    def test_role_filter_drops_nonmatch(self) -> None:
        jobs = self._fetch(
            _account(jobs=[_job(title="Warehouse Forklift Operator")]),
            roles=["data engineer"],
        )
        self.assertEqual(jobs, [])

    def test_company_falls_back_to_slug_when_no_name(self) -> None:
        acct = _account(jobs=[_job()])
        acct["name"] = ""
        with patch.object(self.mod, "_get_json", return_value=acct):
            jobs = self.mod._fetch_company_jobs("acme-labs", ["data engineer"])
        self.assertTrue(jobs[0]["company"])   # cleaned from slug, non-empty
        self.assertNotEqual(jobs[0]["company"], "")

    def test_bad_payload_returns_empty(self) -> None:
        for bad in (None, {}, {"jobs": None}, [], "nope"):
            with patch.object(self.mod, "_get_json", return_value=bad):
                self.assertEqual(self.mod._fetch_company_jobs("acme", ["data engineer"]), [])

    def test_crypto_company_uses_crypto_role_matching(self) -> None:
        # A crypto slug should rescue web3-flavored titles a strict match drops.
        acct = _account(name="Wintermute", jobs=[_job(title="Solidity Engineer")])
        with patch.object(self.mod, "is_crypto_company", return_value=True):
            with patch.object(self.mod, "_get_json", return_value=acct):
                jobs = self.mod._fetch_company_jobs("wintermute", ["engineer"])
        self.assertTrue(any(j["crypto"] for j in jobs))


class WorkableSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import workable as mod
        self.mod = mod

    def test_fan_out_merges_and_caps(self) -> None:
        def fake_fetch(slug, roles, **kw):
            return [_normalized(slug, i) for i in range(4)]
        with patch.object(self.mod, "_fetch_company_jobs", side_effect=fake_fetch):
            out = self.mod.search_workable(
                roles=["data engineer"], companies=["a", "b", "c"], max_results=5,
            )
        self.assertEqual(len(out), 5)   # 3 companies * 4 = 12, capped to 5

    def test_empty_company_list_returns_empty(self) -> None:
        with patch.object(self.mod, "_WORKABLE_COMPANIES", []):
            self.assertEqual(self.mod.search_workable(roles=["x"], companies=[]), [])

    def test_watchlist_is_additive(self) -> None:
        seen: list[str] = []

        def fake_fetch(slug, roles, **kw):
            seen.append(slug)
            return []
        with patch.object(self.mod, "_fetch_company_jobs", side_effect=fake_fetch):
            self.mod.search_workable(
                roles=["x"], companies=["seed1"], watchlist_companies=["seed1", "extra"],
            )
        self.assertIn("seed1", seen)
        self.assertIn("extra", seen)
        self.assertEqual(seen.count("seed1"), 1)   # no dup


def _normalized(slug: str, i: int) -> dict:
    return {"title": f"Data Engineer {i}", "company": slug, "source": "workable"}


class WorkableRegistryTest(unittest.TestCase):
    def test_registered_as_ats(self) -> None:
        from job_finder.tools.scrapers import get_registry
        # Import triggers registration.
        import job_finder.tools.scrapers.workable  # noqa: F401
        reg = get_registry()
        self.assertIn("workable", reg)
        self.assertEqual(reg["workable"].category, "ats")
        self.assertTrue(callable(reg["workable"].search_fn))


if __name__ == "__main__":
    unittest.main()
