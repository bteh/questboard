"""Contract tests for dynamic ATS slug discovery.

Slug discovery harvests company identifiers from DuckDuckGo search results
so the ATS scrapers can grow beyond their hardcoded seed lists. These
tests pin:

- URL parsing per ATS host (no false positives on wrong-host URLs)
- Blocklist filtering (Greenhouse's ``embed`` segment, etc.)
- Cache TTL semantics — fresh skips DDG, stale still returns data but
  triggers a refresh, missing returns empty
- DDGS exception swallowing — discovery never raises
- Union semantics — newly-discovered slugs accumulate with previously
  cached ones (we never forget a slug)
- Disable switch via env var
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


def _fresh_module(cache_dir: Path):
    """Reload the discovery module with a redirected cache dir.

    The module stores its cache path at import time, so swapping cache
    locations between tests requires a reload.
    """
    # Make sure stale state doesn't leak in.
    for mod in list(sys.modules):
        if mod == "job_finder.tools.scrapers._ats_discovery":
            sys.modules.pop(mod, None)
    mod = importlib.import_module("job_finder.tools.scrapers._ats_discovery")
    mod._CACHE_DIR = cache_dir
    return mod


@contextmanager
def _mock_ddgs(results: list[dict] | Exception):
    """Patch the ddgs.DDGS class used inside _ats_discovery.

    Pass a list of result dicts to simulate a successful query, or an
    Exception instance to simulate a DDG failure.
    """
    mock_ddgs_cls = MagicMock()
    instance = MagicMock()
    if isinstance(results, Exception):
        instance.text.side_effect = results
    else:
        instance.text.return_value = list(results)
    mock_ddgs_cls.return_value.__enter__.return_value = instance
    mock_ddgs_cls.return_value.__exit__.return_value = False
    with patch.dict(sys.modules, {"ddgs": MagicMock(DDGS=mock_ddgs_cls)}):
        yield instance


class ExtractSlugTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="lb-ats-discovery-")
        self.mod = _fresh_module(Path(self.tempdir))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_ashby_url(self) -> None:
        slug = self.mod.extract_slug(
            "ashby", "https://jobs.ashbyhq.com/skiffra/e3c2c911-1234"
        )
        self.assertEqual(slug, "skiffra")

    def test_ashby_url_with_query_string(self) -> None:
        slug = self.mod.extract_slug(
            "ashby", "https://jobs.ashbyhq.com/phantom/abc?utm_source=foo"
        )
        self.assertEqual(slug, "phantom")

    def test_greenhouse_legacy_url(self) -> None:
        slug = self.mod.extract_slug(
            "greenhouse", "https://boards.greenhouse.io/openai/jobs/4123"
        )
        self.assertEqual(slug, "openai")

    def test_greenhouse_embed_variant(self) -> None:
        slug = self.mod.extract_slug(
            "greenhouse",
            "https://boards.greenhouse.io/embed/job_app?for=stripe&token=xyz",
        )
        self.assertEqual(slug, "stripe")

    def test_lever_url(self) -> None:
        slug = self.mod.extract_slug(
            "lever", "https://jobs.lever.co/notion/abc-def-123"
        )
        self.assertEqual(slug, "notion")

    def test_wrong_host_returns_none(self) -> None:
        # Greenhouse URL handed to the Ashby regex must not match.
        self.assertIsNone(
            self.mod.extract_slug(
                "ashby", "https://boards.greenhouse.io/openai/jobs/1"
            )
        )

    def test_blocklisted_slug_returns_none(self) -> None:
        # boards.greenhouse.io/embed (not /embed/job_app?for=...) is the
        # ATS's own marketing surface, not a board.
        self.assertIsNone(
            self.mod.extract_slug(
                "greenhouse", "https://boards.greenhouse.io/embed"
            )
        )

    def test_unknown_host_returns_none(self) -> None:
        self.assertIsNone(self.mod.extract_slug("notarealats", "https://anywhere.com"))

    def test_empty_url_returns_none(self) -> None:
        self.assertIsNone(self.mod.extract_slug("ashby", ""))


class CacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="lb-ats-cache-")
        self.cache_dir = Path(self.tempdir)
        self.mod = _fresh_module(self.cache_dir)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_cache(self, host: str, slugs: list[str], discovered_at: datetime) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"ats_discovered_{host}.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "host": host,
                    "discovered_at": discovered_at.isoformat(),
                    "slugs": slugs,
                }
            )
        )

    def test_missing_cache_returns_empty_and_not_fresh(self) -> None:
        slugs, is_fresh = self.mod.load_cached_slugs("ashby")
        self.assertEqual(slugs, set())
        self.assertFalse(is_fresh)

    def test_fresh_cache_round_trip(self) -> None:
        self._write_cache(
            "ashby", ["alpha", "beta"], datetime.now(timezone.utc)
        )
        slugs, is_fresh = self.mod.load_cached_slugs("ashby")
        self.assertEqual(slugs, {"alpha", "beta"})
        self.assertTrue(is_fresh)

    def test_stale_cache_still_returns_data(self) -> None:
        # 10 days old > 7 day TTL
        self._write_cache(
            "ashby", ["alpha"], datetime.now(timezone.utc) - timedelta(days=10)
        )
        slugs, is_fresh = self.mod.load_cached_slugs("ashby")
        self.assertEqual(slugs, {"alpha"})
        self.assertFalse(is_fresh, "Stale cache should report not fresh")

    def test_save_then_load(self) -> None:
        self.mod.save_discovered_slugs("ashby", {"x", "y", "z"})
        slugs, is_fresh = self.mod.load_cached_slugs("ashby")
        self.assertEqual(slugs, {"x", "y", "z"})
        self.assertTrue(is_fresh)

    def test_unreadable_cache_returns_empty(self) -> None:
        path = self.cache_dir / "ats_discovered_ashby.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json {{{")
        slugs, is_fresh = self.mod.load_cached_slugs("ashby")
        self.assertEqual(slugs, set())
        self.assertFalse(is_fresh)


class DiscoverSlugsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="lb-ats-discover-")
        self.mod = _fresh_module(Path(self.tempdir))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_extracts_slugs_from_ddgs_results(self) -> None:
        canned = [
            {"href": "https://jobs.ashbyhq.com/skiffra/e3c2c911-1234"},
            {"href": "https://jobs.ashbyhq.com/phantom/abc?utm_source=x"},
            {"href": "https://example.com/not-ashby"},  # wrong host — skipped
            {"href": "https://jobs.ashbyhq.com/skiffra/another-id"},  # dup slug
        ]
        with _mock_ddgs(canned):
            slugs = self.mod.discover_slugs("ashby", ["ai engineer"])
        self.assertEqual(slugs, {"skiffra", "phantom"})

    def test_empty_roles_returns_empty(self) -> None:
        # Should never hit DDG when no roles are supplied.
        with _mock_ddgs([{"href": "https://jobs.ashbyhq.com/should-not-fire/x"}]) as instance:
            slugs = self.mod.discover_slugs("ashby", [])
        self.assertEqual(slugs, set())
        instance.text.assert_not_called()

    def test_unknown_host_returns_empty(self) -> None:
        with _mock_ddgs([{"href": "https://anywhere"}]):
            self.assertEqual(self.mod.discover_slugs("notarealats", ["x"]), set())

    def test_ddgs_exception_is_swallowed(self) -> None:
        with _mock_ddgs(RuntimeError("DDG is down")):
            slugs = self.mod.discover_slugs("ashby", ["data engineer"])
        self.assertEqual(slugs, set())

    def test_ddgs_exception_on_one_role_keeps_other_results(self) -> None:
        # First call raises, second call returns data. Final result is the
        # union of whatever the non-failing calls produced.
        mock_ddgs_cls = MagicMock()
        instance = MagicMock()
        instance.text.side_effect = [
            RuntimeError("rate limited"),
            [{"href": "https://jobs.ashbyhq.com/recovered-co/foo"}],
        ]
        mock_ddgs_cls.return_value.__enter__.return_value = instance
        mock_ddgs_cls.return_value.__exit__.return_value = False
        with patch.dict(sys.modules, {"ddgs": MagicMock(DDGS=mock_ddgs_cls)}):
            slugs = self.mod.discover_slugs("ashby", ["role-a", "role-b"])
        self.assertEqual(slugs, {"recovered-co"})


class DiscoverAndCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp(prefix="lb-ats-disccache-")
        self.cache_dir = Path(self.tempdir)
        self.mod = _fresh_module(self.cache_dir)
        # Make sure no env override is leaking in.
        os.environ.pop("LAUNCHBOARD_DISABLE_ATS_DISCOVERY", None)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.tempdir, ignore_errors=True)
        os.environ.pop("LAUNCHBOARD_DISABLE_ATS_DISCOVERY", None)

    def _write_cache(self, host: str, slugs: list[str], discovered_at: datetime) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"ats_discovered_{host}.json"
        path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "host": host,
                    "discovered_at": discovered_at.isoformat(),
                    "slugs": slugs,
                }
            )
        )

    def test_fresh_cache_skips_ddg(self) -> None:
        self._write_cache(
            "ashby", ["cached-co"], datetime.now(timezone.utc)
        )
        with _mock_ddgs([{"href": "https://jobs.ashbyhq.com/should-not-appear/x"}]) as instance:
            result = self.mod.discover_and_cache("ashby", ["data engineer"])
        self.assertEqual(result, {"cached-co"})
        instance.text.assert_not_called()

    def test_stale_cache_triggers_refresh_and_unions(self) -> None:
        self._write_cache(
            "ashby",
            ["old-co"],
            datetime.now(timezone.utc) - timedelta(days=10),
        )
        canned = [{"href": "https://jobs.ashbyhq.com/new-co/job-id"}]
        with _mock_ddgs(canned) as instance:
            result = self.mod.discover_and_cache("ashby", ["data engineer"])
        # New + old slugs should both end up in the result and the cache file.
        self.assertEqual(result, {"old-co", "new-co"})
        instance.text.assert_called()

        # Re-read the cache to confirm the persisted state matches.
        slugs, is_fresh = self.mod.load_cached_slugs("ashby")
        self.assertEqual(slugs, {"old-co", "new-co"})
        self.assertTrue(is_fresh)

    def test_missing_cache_creates_one(self) -> None:
        canned = [{"href": "https://jobs.ashbyhq.com/first-co/job-id"}]
        with _mock_ddgs(canned):
            result = self.mod.discover_and_cache("ashby", ["data engineer"])
        self.assertEqual(result, {"first-co"})
        # Cache file should now exist.
        self.assertTrue((self.cache_dir / "ats_discovered_ashby.json").exists())

    def test_no_roles_returns_cached_without_ddg_call(self) -> None:
        self._write_cache(
            "ashby",
            ["old-co"],
            datetime.now(timezone.utc) - timedelta(days=10),
        )
        with _mock_ddgs([{"href": "ignored"}]) as instance:
            result = self.mod.discover_and_cache("ashby", [])
        self.assertEqual(result, {"old-co"})
        instance.text.assert_not_called()

    def test_env_var_disables_discovery(self) -> None:
        self._write_cache(
            "ashby",
            ["cached-co"],
            datetime.now(timezone.utc) - timedelta(days=10),
        )
        os.environ["LAUNCHBOARD_DISABLE_ATS_DISCOVERY"] = "1"
        with _mock_ddgs([{"href": "https://jobs.ashbyhq.com/skiprun/x"}]) as instance:
            result = self.mod.discover_and_cache("ashby", ["data engineer"])
        self.assertEqual(result, {"cached-co"})
        instance.text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
