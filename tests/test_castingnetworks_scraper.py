"""Contract tests for the Casting Networks quest scraper (vertical "camera").

The fixtures are trimmed REAL responses probed live 2026-07-08 (HTTP 200):
the /casting-calls/ listing (ItemList cut from 8 roles to 3) and one role
page whose JobPosting block is kept verbatim. These tests pin the listing
ItemList walk, the JobPosting-to-row mapping, the no-salary-keys rule when
the source states no pay, the baseSalary path, the quest extras (role id,
valid-through, age bounds, union, applicant country), explicit-only
first_quest_ok, ordering, graceful degradation, and registry registration
under the camera vertical.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

LISTING_FIXTURE = ROOT / "tests" / "fixtures" / "castingnetworks_listing.html"
ROLE_FIXTURE = ROOT / "tests" / "fixtures" / "castingnetworks_role.html"

_HOST_URL = "https://www.castingnetworks.com/talent/project/16047383/role/67439981"
_FEMALE_URL = "https://www.castingnetworks.com/talent/project/16047441/role/67440215"
_ATLANTA_URL = "https://www.castingnetworks.com/talent/project/16048613/role/67446117"

# Real JobPosting from the Host role page (live probe 2026-07-08), description
# trimmed. No jobLocation and no baseSalary: the page states neither.
_HOST_POSTING: dict = {
    "@context": "https://schema.org/",
    "@type": "JobPosting",
    "url": _HOST_URL + "/",
    "title": "Host - Major Philanthropy Youtube Channel",
    "description": (
        "We are currently looking for hosts who are comfortable in front of "
        "the camera and who have a genuine interest in philanthropy. It is a "
        "paid one year commitment, that will involve lots of travel to "
        "developing countries."
    ),
    "datePosted": "2026-07-03T00:49:21Z",
    "validThrough": "2026-07-24T00:00:00Z",
    "employmentType": "CONTRACTOR",
    "directApply": True,
    "jobLocationType": "ON_SITE",
    "industry": "Entertainment",
    "hiringOrganization": {"@type": "Organization", "name": "Casting Networks"},
    "applicantLocationRequirements": {"@type": "Country", "name": "United States"},
    "identifier": {
        "@type": "PropertyValue",
        "name": "CastingNetworks Role ID",
        "value": "67439981",
    },
}


def _page(*nodes: dict) -> str:
    """Wrap JSON-LD nodes in a minimal role-page HTML shell."""
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(n)}</script>'
        for n in nodes
    )
    return f"<html><head>{scripts}</head><body></body></html>"


def _fake_get_html(pages: dict[str, str]):
    def fake(url: str) -> str:
        return pages.get(url.rstrip("/"), "")
    return fake


class ListingParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import castingnetworks as mod
        self.mod = mod

    def test_extracts_role_urls_in_listing_order(self) -> None:
        urls = self.mod._listing_role_urls(LISTING_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(urls, [_HOST_URL, _FEMALE_URL, _ATLANTA_URL])

    def test_ignores_non_role_urls(self) -> None:
        html = _page({
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "item": {"url": "https://www.castingnetworks.com/blog/"}},
                {"@type": "ListItem", "item": {"url": _HOST_URL}},
                "not-a-dict",
            ],
        })
        self.assertEqual(self.mod._listing_role_urls(html), [_HOST_URL])

    def test_dedupes_trailing_slash_variants(self) -> None:
        html = _page({
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "item": {"url": _HOST_URL}},
                {"@type": "ListItem", "item": {"url": _HOST_URL + "/"}},
            ],
        })
        self.assertEqual(self.mod._listing_role_urls(html), [_HOST_URL])

    def test_bad_html_returns_empty(self) -> None:
        for bad in ("", "<html></html>", '<script type="application/ld+json">nope</script>'):
            self.assertEqual(self.mod._listing_role_urls(bad), [])


class RoleParseTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import castingnetworks as mod
        self.mod = mod

    def _fetch(self, html: str, url: str = _ATLANTA_URL) -> dict | None:
        with patch.object(self.mod, "_get_html", return_value=html):
            return self.mod._fetch_role(url)

    def test_parses_fixture_role(self) -> None:
        row = self._fetch(ROLE_FIXTURE.read_text(encoding="utf-8"))
        assert row is not None
        self.assertEqual(
            row["title"],
            "College Looking Background Needed in Atlanta  - Non Union Background Needed in Atlanta",
        )
        self.assertEqual(row["company"], "Casting Networks")
        self.assertEqual(row["location"], "Atlanta, GA")
        self.assertEqual(row["url"], _ATLANTA_URL + "/")
        self.assertEqual(row["source"], "castingnetworks")
        self.assertEqual(row["vertical"], "camera")
        self.assertEqual(row["date_posted"], "2026-07-08T03:36:26Z")
        self.assertIn("College looking background", row["description"])

    def test_no_salary_keys_when_source_states_none(self) -> None:
        row = self._fetch(ROLE_FIXTURE.read_text(encoding="utf-8"))
        assert row is not None
        for key in ("salary_min", "salary_max", "salary_period", "salary_source"):
            self.assertNotIn(key, row)

    def test_quest_extras_from_fixture(self) -> None:
        row = self._fetch(ROLE_FIXTURE.read_text(encoding="utf-8"))
        assert row is not None
        q = row["quest"]
        self.assertEqual(q["role_id"], "67446117")
        self.assertEqual(q["valid_through"], "2026-07-15T00:00:00Z")
        self.assertEqual(q["age_min"], 18)
        self.assertEqual(q["age_max"], 30)
        self.assertEqual(q["union"], "non-union")
        self.assertNotIn("applicant_country", q)  # page states jobLocation instead

    def test_host_posting_without_job_location(self) -> None:
        row = self._fetch(_page(_HOST_POSTING), url=_HOST_URL)
        assert row is not None
        self.assertEqual(row["location"], "")  # not stated, never invented
        self.assertEqual(row["quest"]["applicant_country"], "United States")
        self.assertNotIn("first_quest_ok", row)
        self.assertNotIn("is_rolling", row)  # dated calls, not a standing platform

    def test_first_quest_only_when_stated(self) -> None:
        posting = dict(_HOST_POSTING)
        posting["description"] = "Background extras wanted. No experience necessary."
        row = self._fetch(_page(posting), url=_HOST_URL)
        assert row is not None
        self.assertTrue(row["first_quest_ok"])

    def test_base_salary_maps_to_reported_pay(self) -> None:
        posting = dict(_HOST_POSTING)
        posting["baseSalary"] = {
            "@type": "MonetaryAmount",
            "currency": "USD",
            "value": {
                "@type": "QuantitativeValue",
                "minValue": 150,
                "maxValue": 200,
                "unitText": "DAY",
            },
        }
        row = self._fetch(_page(posting), url=_HOST_URL)
        assert row is not None
        self.assertEqual(row["salary_min"], 150.0)
        self.assertEqual(row["salary_max"], 200.0)
        self.assertEqual(row["salary_period"], "daily")
        self.assertEqual(row["salary_source"], "reported")

    def test_skips_posting_without_title(self) -> None:
        posting = dict(_HOST_POSTING)
        posting["title"] = ""
        self.assertIsNone(self._fetch(_page(posting), url=_HOST_URL))

    def test_none_when_page_has_no_jobposting(self) -> None:
        self.assertIsNone(self._fetch(_page({"@type": "WebPage", "name": "x"})))

    def test_none_when_fetch_fails(self) -> None:
        self.assertIsNone(self._fetch(""))


class SalaryHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import castingnetworks as mod
        self.mod = mod

    def test_single_value_with_unit(self) -> None:
        base = {"value": {"value": 45, "unitText": "HOUR"}}
        self.assertEqual(self.mod._extract_salary(base), (45.0, 45.0, "hourly"))

    def test_plain_number_value(self) -> None:
        self.assertEqual(self.mod._extract_salary({"value": 500}), (500.0, 500.0, None))

    def test_absent_or_bad(self) -> None:
        for bad in (None, "x", {}, {"value": None}, {"value": {"value": "abc"}}, {"value": 0}):
            self.assertEqual(self.mod._extract_salary(bad), (None, None, None))


class SearchFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        from job_finder.tools.scrapers import castingnetworks as mod
        self.mod = mod
        self.listing_html = LISTING_FIXTURE.read_text(encoding="utf-8")
        self.role_html = ROLE_FIXTURE.read_text(encoding="utf-8")

    def test_search_merges_and_keeps_listing_order(self) -> None:
        pages = {
            self.mod._LISTING_URL.rstrip("/"): self.listing_html,
            _HOST_URL: _page(_HOST_POSTING),
            _ATLANTA_URL: self.role_html,
            # Female Talent page fails: the row degrades away, others survive.
        }
        with patch.object(self.mod, "_get_html", side_effect=_fake_get_html(pages)):
            rows = self.mod.search_castingnetworks(roles=["data engineer"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["url"], _HOST_URL + "/")   # listing order restored
        self.assertEqual(rows[1]["url"], _ATLANTA_URL + "/")
        self.assertTrue(all(r["vertical"] == "camera" for r in rows))

    def test_max_results_caps_role_fetches(self) -> None:
        fetched: list[str] = []
        pages = {
            self.mod._LISTING_URL.rstrip("/"): self.listing_html,
            _HOST_URL: _page(_HOST_POSTING),
        }
        fake = _fake_get_html(pages)

        def tracking(url: str) -> str:
            fetched.append(url)
            return fake(url)

        with patch.object(self.mod, "_get_html", side_effect=tracking):
            rows = self.mod.search_castingnetworks(max_results=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(fetched), 2)   # listing + one role page only

    def test_listing_failure_returns_empty(self) -> None:
        with patch.object(self.mod, "_get_html", return_value=""):
            self.assertEqual(self.mod.search_castingnetworks(), [])

    def test_all_role_pages_failing_returns_empty(self) -> None:
        pages = {self.mod._LISTING_URL.rstrip("/"): self.listing_html}
        with patch.object(self.mod, "_get_html", side_effect=_fake_get_html(pages)):
            self.assertEqual(self.mod.search_castingnetworks(), [])


class CastingNetworksRegistryTest(unittest.TestCase):
    def test_registered_as_camera_quest_scraper(self) -> None:
        from job_finder.tools.scrapers import get_registry
        from job_finder.tools.scrapers._registry import default_scraper_names
        import job_finder.tools.scrapers.castingnetworks  # noqa: F401

        reg = get_registry()
        self.assertIn("castingnetworks", reg)
        meta = reg["castingnetworks"]
        self.assertEqual(meta.vertical, "camera")
        self.assertEqual(meta.category, "quest")
        self.assertFalse(meta.enabled_by_default)
        self.assertTrue(callable(meta.search_fn))
        # Quest scrapers never join the default career sweep.
        self.assertNotIn("castingnetworks", default_scraper_names())


if __name__ == "__main__":
    unittest.main()
