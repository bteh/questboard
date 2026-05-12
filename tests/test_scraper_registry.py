from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from job_finder.tools.scrapers._registry import ScraperMeta, run_scrapers

registry_module = importlib.import_module("job_finder.tools.scrapers._registry")


class ScraperRegistryTest(unittest.TestCase):
    def test_ats_scrapers_run_on_seed_list_when_no_user_watchlist(self) -> None:
        """ATS scrapers (Greenhouse/Lever/Ashby) ship with curated seed lists
        of 100+ high-signal companies. They were previously skipped entirely
        when the user had no watchlist, which made all that seed data dead
        code. Now they always run; the search_fn's own logic falls back to
        the seed list when watchlist_companies is empty."""
        greenhouse = Mock(return_value=[{"title": "Seeded greenhouse job"}])
        lever = Mock(return_value=[{"title": "Seeded lever job"}])
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

        # All three scrapers ran; seed-based jobs are returned.
        self.assertEqual(len(jobs), 3)
        greenhouse.assert_called_once()
        lever.assert_called_once()
        builtin.assert_called_once()
        # ATS scrapers should NOT be passed watchlist_companies when empty —
        # they fall back to their built-in seed list.
        self.assertNotIn("watchlist_companies", greenhouse.call_args.kwargs)
        self.assertNotIn("watchlist_companies", lever.call_args.kwargs)
        self.assertTrue(any("Searching 3 additional sources" in msg for msg in progress))
        # No "skipped" messages now — the previous gating is gone.
        self.assertFalse(any("skipped — no companies" in msg for msg in progress))

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
