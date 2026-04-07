from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from job_finder.tools.scrapers._registry import ScraperMeta, run_scrapers

registry_module = importlib.import_module("job_finder.tools.scrapers._registry")


class ScraperRegistryTest(unittest.TestCase):
    def test_ats_scrapers_without_company_watchlist_are_skipped(self) -> None:
        greenhouse = Mock(return_value=[{"title": "Should not run"}])
        lever = Mock(return_value=[{"title": "Should not run"}])
        builtin = Mock(return_value=[{"title": "BuiltIn job"}])
        progress: list[str] = []

        registry = {
            "greenhouse": ScraperMeta(
                name="greenhouse",
                display_name="Greenhouse",
                url="https://greenhouse.io",
                description="",
                category="ats",
                enabled_by_default=True,
                search_fn=greenhouse,
            ),
            "lever": ScraperMeta(
                name="lever",
                display_name="Lever",
                url="https://lever.co",
                description="",
                category="ats",
                enabled_by_default=True,
                search_fn=lever,
            ),
            "builtin": ScraperMeta(
                name="builtin",
                display_name="BuiltIn",
                url="https://builtin.com",
                description="",
                category="general",
                enabled_by_default=True,
                search_fn=builtin,
            ),
        }

        with patch.dict(registry_module._REGISTRY, registry, clear=True):
            jobs = run_scrapers(
                names=["greenhouse", "lever", "builtin"],
                roles=["data engineer"],
                progress=progress.append,
                watchlist_by_ats={},
            )

        self.assertEqual(jobs, [{"title": "BuiltIn job"}])
        greenhouse.assert_not_called()
        lever.assert_not_called()
        builtin.assert_called_once()
        self.assertTrue(any("Searching 1 additional sources" in msg for msg in progress))
        self.assertTrue(any("Greenhouse: skipped" in msg for msg in progress))
        self.assertTrue(any("Lever: skipped" in msg for msg in progress))

    def test_ats_scrapers_run_when_company_watchlist_is_present(self) -> None:
        greenhouse = Mock(return_value=[{"title": "OpenAI job"}])
        progress: list[str] = []

        registry = {
            "greenhouse": ScraperMeta(
                name="greenhouse",
                display_name="Greenhouse",
                url="https://greenhouse.io",
                description="",
                category="ats",
                enabled_by_default=True,
                search_fn=greenhouse,
            ),
        }

        with patch.dict(registry_module._REGISTRY, registry, clear=True):
            jobs = run_scrapers(
                names=["greenhouse"],
                roles=["research engineer"],
                progress=progress.append,
                watchlist_by_ats={"greenhouse": ["openai"]},
            )

        self.assertEqual(jobs, [{"title": "OpenAI job"}])
        greenhouse.assert_called_once()
        self.assertEqual(greenhouse.call_args.kwargs["watchlist_companies"], ["openai"])
        self.assertTrue(any("Searching 1 additional sources" in msg for msg in progress))
        self.assertTrue(any("Found 1 jobs from Greenhouse" in msg for msg in progress))


if __name__ == "__main__":
    unittest.main()
