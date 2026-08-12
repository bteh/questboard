from __future__ import annotations

import importlib
import threading
import time
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

        # Patch the discovery hook so this test stays deterministic — no
        # real DDG calls. Empty return means scrapers fall back to seed only.
        from job_finder.tools.scrapers import _ats_discovery

        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(_ats_discovery, "discover_and_cache", return_value=set()), \
             patch.object(_ats_discovery, "verified_rotation_slugs", return_value=set()):
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

        # Patch discovery to return empty so we test the explicit-watchlist
        # path without DDG interference.
        from job_finder.tools.scrapers import _ats_discovery

        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(_ats_discovery, "discover_and_cache", return_value=set()), \
             patch.object(_ats_discovery, "verified_rotation_slugs", return_value=set()):
            jobs = run_scrapers(
                names=["greenhouse"],
                roles=["research engineer"],
                progress=progress.append,
                watchlist_by_ats={"greenhouse": ["openai"]},
            )

        # run_scrapers post-processing adds the contract fields
        # (date_confidence / salary_source / work_type_confidence) on top of
        # whatever the scraper returned.
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "OpenAI job")
        self.assertEqual(jobs[0]["date_confidence"], "missing")
        self.assertIsNone(jobs[0]["salary_source"])
        self.assertEqual(jobs[0]["work_type_confidence"], "inferred")
        greenhouse.assert_called_once()
        self.assertEqual(greenhouse.call_args.kwargs["watchlist_companies"], ["openai"])
        self.assertTrue(any("Searching 1 additional sources" in msg for msg in progress))
        self.assertTrue(any("Found 1 jobs from Greenhouse" in msg for msg in progress))


    def test_discovered_slugs_merge_into_user_watchlist(self) -> None:
        """ATS discovery's output should be unioned with the user's watchlist
        and handed to the search_fn via watchlist_companies. Existing user
        entries must survive the union — discovery is additive only."""
        greenhouse = Mock(return_value=[{"title": "Some greenhouse job"}])
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

        # Patch the lazy-imported discovery hook to return a deterministic set
        # without actually hitting DDG.
        from job_finder.tools.scrapers import _ats_discovery

        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(_ats_discovery, "discover_and_cache",
                          return_value={"discovered-co", "openai"}), \
             patch.object(_ats_discovery, "verified_rotation_slugs", return_value=set()):
            run_scrapers(
                names=["greenhouse"],
                roles=["research engineer"],
                progress=progress.append,
                watchlist_by_ats={"greenhouse": ["openai", "user-only-co"]},
            )

        greenhouse.assert_called_once()
        # User's watchlist (openai, user-only-co) is unioned with discovered
        # (discovered-co, openai). Final passed list should be sorted and
        # deduplicated.
        self.assertEqual(
            sorted(greenhouse.call_args.kwargs["watchlist_companies"]),
            ["discovered-co", "openai", "user-only-co"],
        )
        # Progress message should announce the new discoveries.
        self.assertTrue(
            any("discovered" in msg.lower() for msg in progress),
            f"Expected a 'discovered' progress message, got: {progress}",
        )

    def test_no_roles_skips_discovery(self) -> None:
        """When the caller doesn't pass roles, discovery must not fire —
        otherwise we'd run DDG queries on empty strings every search."""
        greenhouse = Mock(return_value=[])
        from job_finder.tools.scrapers import _ats_discovery

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

        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(_ats_discovery, "discover_and_cache") as mock_disc:
            run_scrapers(
                names=["greenhouse"],
                roles=None,
                progress=[].append,
                watchlist_by_ats={},
            )

        mock_disc.assert_not_called()

    def test_hung_source_cannot_block_healthy_source_or_run_log(self) -> None:
        blocker = threading.Event()
        progress: list[str] = []
        recorded: list[dict] = []
        receipt: list[dict] = []

        def hung(**_kwargs):
            blocker.wait(10)
            return []

        registry = {
            "fast": ScraperMeta(
                name="fast", display_name="Fast", url="https://fast.example",
                description="", category="general", enabled_by_default=True,
                search_fn=Mock(return_value=[{"title": "Fast job"}]),
            ),
            "hung": ScraperMeta(
                name="hung", display_name="Hung", url="https://hung.example",
                description="", category="general", enabled_by_default=True,
                search_fn=hung,
            ),
        }

        from job_finder.models import database as database_module

        started = time.monotonic()
        with patch.dict(registry_module._REGISTRY, registry, clear=True), \
             patch.object(registry_module, "_SCRAPER_POOL_TIMEOUT_SECONDS", 0.05), \
             patch.object(database_module, "record_scrape_runs", side_effect=recorded.extend):
            jobs = run_scrapers(
                names=["fast", "hung"],
                progress=progress.append,
                outcome_sink=receipt,
            )

        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual([job["title"] for job in jobs], ["Fast job"])
        by_source = {row["source"]: row for row in recorded}
        self.assertEqual(by_source["fast"]["finish_reason"], "ok")
        self.assertEqual(by_source["hung"]["finish_reason"], "timeout")
        self.assertEqual({row["source"] for row in receipt}, {"fast", "hung"})
        self.assertTrue(any("Hung: timed out" in msg for msg in progress))


if __name__ == "__main__":
    unittest.main()
