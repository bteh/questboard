"""Contract tests: strictness preset reaches the per-scraper role filter.

PR #11 (filter strictness) plumbed ``match_mode`` and ``include_founding``
through the pipeline-level ``filter_by_role``. But the 13+ individual
scrapers each call ``_match_roles(title, roles)`` *directly* with no
kwargs, so they were silently defaulting to ``"all_significant"`` mode
regardless of what the user picked.

Real-world impact (verified by live probe):
- ``loose`` strictness should accept "Research Engineer" for role
  ``"ai engineer"`` (any-word overlap). Default strict mode rejected it,
  causing ~95% of ATS results to drop inside the scraper.

This test pins the contract: ``run_scrapers(..., filters=settings)``
threads ``role_match_mode`` and ``include_founding_titles`` into every
search_fn's kwargs, and each scraper forwards them to its
``_match_roles`` calls.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers._registry import ScraperMeta, run_scrapers

registry_module = importlib.import_module("job_finder.tools.scrapers._registry")


def _make_meta(name: str, search_fn) -> ScraperMeta:
    return ScraperMeta(
        name=name,
        display_name=name.title(),
        url=f"https://{name}.example",
        description="",
        category="general",
        enabled_by_default=True,
        search_fn=search_fn,
    )


class StrictnessPropagationTest(unittest.TestCase):
    def _run(self, *, filters, watchlist_by_ats=None):
        captured: dict = {}

        def fake_scraper(**kwargs):
            captured.update(kwargs)
            return []

        with patch.dict(
            registry_module._REGISTRY,
            {"remoteok": _make_meta("remoteok", fake_scraper)},
            clear=True,
        ):
            run_scrapers(
                names=["remoteok"],
                roles=["ai engineer"],
                filters=filters,
                watchlist_by_ats=watchlist_by_ats or {},
            )
        return captured

    def test_loose_preset_passes_any_word_to_scraper(self) -> None:
        kwargs = self._run(filters={
            "role_match_mode": "any_word",
            "include_founding_titles": True,
        })
        self.assertEqual(kwargs.get("match_mode"), "any_word")
        self.assertTrue(kwargs.get("include_founding"))

    def test_strict_preset_passes_exact_to_scraper(self) -> None:
        kwargs = self._run(filters={
            "role_match_mode": "exact",
            "include_founding_titles": False,
        })
        self.assertEqual(kwargs.get("match_mode"), "exact")
        self.assertFalse(kwargs.get("include_founding"))

    def test_missing_filters_uses_safe_defaults(self) -> None:
        kwargs = self._run(filters=None)
        # When the caller passes no filters, scrapers must still get the
        # safe defaults — not None — so the kwargs don't conflict with
        # each scraper's parameter defaults.
        self.assertEqual(kwargs.get("match_mode"), "all_significant")
        self.assertTrue(kwargs.get("include_founding"))


class ScraperHonorsMatchModeTest(unittest.TestCase):
    """Each scraper's _match_roles call must honor the kwargs it receives.

    Smoke-tests every scraper that takes a list of jobs in-memory — we
    feed them a mock HTTP response and verify they emit jobs matching
    titles only when the role-match mode permits.
    """

    def test_remoteok_honors_match_mode(self) -> None:
        from job_finder.tools.scrapers import remoteok

        fake_data = [
            {"legal": "..."},  # first item is always a legal notice — skipped
            {
                "position": "Research Engineer",
                "company": "Acme",
                "location": "Remote",
                "url": "https://example.com/1",
                "id": "1",
                "date": "2025-01-01",
            },
        ]
        with patch.object(remoteok, "_get_json", return_value=fake_data):
            strict = remoteok.search_remoteok(
                roles=["ai engineer"],
                match_mode="all_significant",
                include_founding=False,
            )
            loose = remoteok.search_remoteok(
                roles=["ai engineer"],
                match_mode="any_word",
                include_founding=False,
            )
        self.assertEqual(len(strict), 0, "Strict mode should drop 'Research Engineer'")
        self.assertEqual(len(loose), 1, "Loose any_word should accept 'Research Engineer'")
        self.assertEqual(loose[0]["title"], "Research Engineer")

    def test_himalayas_honors_match_mode(self) -> None:
        from job_finder.tools.scrapers import himalayas

        fake_page = {
            "jobs": [
                {
                    "title": "Software Engineer, Platform",
                    "companyName": "Acme",
                    "guid": "g1",
                    "applicationLink": "https://example.com/1",
                    "publishedDate": "2025-01-01",
                    "categories": ["Engineering"],
                },
            ],
        }
        empty_page = {"jobs": []}
        # Himalayas paginates; first call returns the canned page, second is empty.
        with patch.object(himalayas, "_get_json", side_effect=[fake_page, empty_page]):
            strict = himalayas.search_himalayas(
                roles=["ai engineer"],
                max_results=20,
                match_mode="all_significant",
                include_founding=False,
            )

        with patch.object(himalayas, "_get_json", side_effect=[fake_page, empty_page]):
            loose = himalayas.search_himalayas(
                roles=["ai engineer"],
                max_results=20,
                match_mode="any_word",
                include_founding=False,
            )

        self.assertEqual(len(strict), 0)
        self.assertEqual(len(loose), 1)


if __name__ == "__main__":
    unittest.main()
