"""Workday must honor the user's watchlist and rank before every truncation.

Bug (2026-08-17 audit): the registry's _ats_scrapers set omitted "workday",
so watchlist tokens never reached search_workday, which swallowed them via
**kwargs anyway. Its universe was permanently the ~26 YAML tenants, and both
truncations (per-employer and the final [:max_results]) kept arbitrary
fetch-order rows. Prodege's and Workiva's "Staff Data Engineer" postings were
both missed. The fix: workday joins the ATS watchlist plumbing, watchlist
tokens resolve to {tenant, site_id, base_url} (careers URL, tenant/site
token, or fuzzy YAML name), watchlist employers get WATCHLIST_TIMEOUT and
protected rows, and every truncation goes through rank_by_relevance /
cap_with_protected.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import workday
from job_finder.tools.scrapers._utils import PROTECTED_ROW_KEY, WATCHLIST_TIMEOUT

ROLES = ["data engineer"]

SEEDCO = {
    "name": "SeedCo",
    "tenant": "seedco",
    "site_id": "SeedSite",
    "base_url": "https://seedco.wd1.myworkdayjobs.com",
}
NVIDIA = {
    "name": "NVIDIA",
    "tenant": "nvidia",
    "site_id": "NVIDIAExternalCareerSite",
    "base_url": "https://nvidia.wd5.myworkdayjobs.com",
}
CAPITALONE = {
    "name": "Capital One",
    "tenant": "capitalone",
    "site_id": "Capital_One",
    "base_url": "https://capitalone.wd12.myworkdayjobs.com",
}

PRODEGE_URL = "https://prodege.wd108.myworkdayjobs.com/Prodege_Careers"


def _payload(titles: list[str]) -> dict:
    return {
        "jobPostings": [
            {
                "title": title,
                "externalPath": f"/job/x/{i}",
                "locationsText": "Los Angeles, CA",
                "postedOn": "Posted Today",
            }
            for i, title in enumerate(titles)
        ]
    }


def _detail(*_args, **_kwargs) -> dict:
    return {"jobPostingInfo": {"jobDescription": "<p>a role</p>"}}


class RegistryPassesWatchlistToWorkdayTest(unittest.TestCase):
    """run_scrapers must treat workday as an ATS scraper."""

    def test_workday_receives_watchlist_companies_kwarg(self) -> None:
        import importlib

        from job_finder.tools.scrapers._registry import ScraperMeta, run_scrapers
        from job_finder.tools.scrapers import _ats_discovery

        registry_module = importlib.import_module(
            "job_finder.tools.scrapers._registry"
        )
        fn = Mock(return_value=[{"title": "Prodege job"}])
        registry = {
            "workday": ScraperMeta(
                name="workday",
                display_name="Workday Careers",
                url="https://myworkdayjobs.com",
                description="",
                category="ats",
                enabled_by_default=True,
                search_fn=fn,
            ),
        }
        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
                patch.object(_ats_discovery, "discover_and_cache", return_value=set()), \
                patch.object(_ats_discovery, "verified_rotation_slugs", return_value=set()):
            run_scrapers(
                names=["workday"],
                roles=ROLES,
                watchlist_by_ats={"workday": [PRODEGE_URL]},
            )
        fn.assert_called_once()
        self.assertEqual(
            fn.call_args.kwargs.get("watchlist_companies"), [PRODEGE_URL]
        )


class WorkdayWatchlistResolveTest(unittest.TestCase):
    """Watchlist tokens must resolve to a queryable {tenant, site_id, base_url}."""

    def _run(self, employers: dict, tokens: list[str], max_results: int = 50):
        seen: dict[str, dict] = {}

        def fake_search(employer, query, limit=20, offset=0, timeout=None):
            seen[employer["tenant"]] = {
                "site_id": employer["site_id"],
                "base_url": employer["base_url"],
                "timeout": timeout,
            }
            return _payload(["Data Engineer"])

        with patch.object(workday, "_load_employers", return_value=employers), \
                patch.object(workday, "_api_search", side_effect=fake_search), \
                patch.object(workday, "_api_detail", side_effect=_detail):
            rows = workday.search_workday(
                roles=ROLES, max_results=max_results, watchlist_companies=tokens,
            )
        return seen, rows

    def test_careers_url_token_derives_tenant_site_and_host(self) -> None:
        seen, _ = self._run(dict(seedco=SEEDCO), [PRODEGE_URL])
        self.assertIn("prodege", seen)
        self.assertEqual(seen["prodege"]["site_id"], "Prodege_Careers")
        self.assertEqual(
            seen["prodege"]["base_url"], "https://prodege.wd108.myworkdayjobs.com"
        )
        self.assertEqual(seen["prodege"]["timeout"], WATCHLIST_TIMEOUT)
        self.assertNotEqual(seen["seedco"]["timeout"], WATCHLIST_TIMEOUT)

    def test_tenant_site_token_resolves_host_via_yaml(self) -> None:
        """The paste path stores 'tenant/site' (no wd host); the YAML entry
        for the same tenant supplies the host."""
        seen, _ = self._run(
            dict(seedco=SEEDCO, nvidia=NVIDIA),
            ["nvidia/NVIDIAExternalCareerSite"],
        )
        self.assertEqual(seen["nvidia"]["timeout"], WATCHLIST_TIMEOUT)
        self.assertEqual(
            seen["nvidia"]["base_url"], "https://nvidia.wd5.myworkdayjobs.com"
        )

    def test_bare_name_token_fuzzy_matches_yaml(self) -> None:
        seen, _ = self._run(
            dict(seedco=SEEDCO, capitalone=CAPITALONE), ["Capital One"],
        )
        self.assertEqual(seen["capitalone"]["timeout"], WATCHLIST_TIMEOUT)

    def test_unresolvable_token_warns_instead_of_vanishing(self) -> None:
        with self.assertLogs(workday.logger, level="WARNING") as logs:
            self._run(dict(seedco=SEEDCO), ["totally-unknown-co"])
        self.assertTrue(any("totally-unknown-co" in line for line in logs.output))


class WorkdayProtectedRowsTest(unittest.TestCase):
    """Watchlist rows survive the final cap and never leak the flag."""

    def _run(self):
        def fake_search(employer, query, limit=20, offset=0, timeout=None):
            if employer["tenant"] == "prodege":
                return _payload(["Manager of Data Engineering"])
            return _payload(
                ["Data Engineer", "Senior Data Engineer", "Staff Data Engineer"]
            )

        with patch.object(workday, "_load_employers", return_value=dict(seedco=SEEDCO)), \
                patch.object(workday, "_api_search", side_effect=fake_search), \
                patch.object(workday, "_api_detail", side_effect=_detail):
            return workday.search_workday(
                roles=ROLES, max_results=3, watchlist_companies=[PRODEGE_URL],
            )

    def test_watchlist_row_survives_the_source_cap(self) -> None:
        titles = [r["title"] for r in self._run()]
        self.assertIn("Manager of Data Engineering", titles)

    def test_protected_flag_never_leaks(self) -> None:
        self.assertTrue(all(PROTECTED_ROW_KEY not in r for r in self._run()))


class WorkdayRankedTruncationTest(unittest.TestCase):
    """Both truncations keep the strongest matches, not fetch-order rows."""

    def test_role_match_fetched_last_survives_per_employer_cap(self) -> None:
        employers = {
            "a": dict(SEEDCO, tenant="a", name="A"),
            "b": dict(SEEDCO, tenant="b", name="B"),
        }

        def fake_search(employer, query, limit=20, offset=0, timeout=None):
            if employer["tenant"] == "a":
                # 29 broad-fallback rows first, the only real match dead last.
                return _payload(["Senior Accountant"] * 29 + ["Data Engineer"])
            return _payload(["Senior Data Engineer"] * 3)

        with patch.object(workday, "_load_employers", return_value=employers), \
                patch.object(workday, "_api_search", side_effect=fake_search), \
                patch.object(workday, "_api_detail", side_effect=_detail):
            rows = workday.search_workday(roles=ROLES, max_results=6)
        titles = [r["title"] for r in rows]
        self.assertIn("Data Engineer", titles)

    def test_final_cap_is_relevance_ranked_across_employers(self) -> None:
        employers = {
            "a": dict(SEEDCO, tenant="a", name="A"),
            "b": dict(SEEDCO, tenant="b", name="B"),
        }

        def fake_search(employer, query, limit=20, offset=0, timeout=None):
            if employer["tenant"] == "a":
                return _payload(["Senior Accountant"] * 3)
            return _payload(["Data Engineer"] * 3)

        with patch.object(workday, "_load_employers", return_value=employers), \
                patch.object(workday, "_MAX_EMPLOYER_WORKERS", 1), \
                patch.object(workday, "_api_search", side_effect=fake_search), \
                patch.object(workday, "_api_detail", side_effect=_detail):
            rows = workday.search_workday(roles=ROLES, max_results=3)
        titles = [r["title"] for r in rows]
        self.assertEqual(titles.count("Data Engineer"), 3)


if __name__ == "__main__":
    unittest.main()
