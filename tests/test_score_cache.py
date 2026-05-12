"""Contract tests for the per-job AI scoring disk cache.

The cache short-circuits LLM calls when the same job has already been
scored against the same resume + weights. These tests pin:

1. Stable-input → same cache key. Reordered ``scoring_config`` dict keys
   don't change the key (JSON serialised with ``sort_keys``).
2. Any input change (resume, description, weights, workspace) → different key.
3. ``load_cached`` returns ``None`` on missing/corrupt/expired entries
   and the saved dict on a fresh hit.
4. ``save_cached`` writes atomically and is a no-op for empty/non-dict input.
5. ``LAUNCHBOARD_DISABLE_AI_SCORE_CACHE`` blocks both reads and writes.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


class ScoreCacheKeyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = importlib.import_module("job_finder.scoring.score_cache")

    def test_same_inputs_same_key(self) -> None:
        job = {"url": "https://x/a", "description": "build APIs"}
        cfg = {"weights": {"technical": 0.25, "leadership": 0.15}}
        k1 = self.mod.cache_key("ws1", "resume body", job, cfg)
        k2 = self.mod.cache_key("ws1", "resume body", job, cfg)
        self.assertEqual(k1, k2)

    def test_key_invariant_under_dict_reordering(self) -> None:
        job = {"url": "https://x/a", "description": "build APIs"}
        cfg_a = {"weights": {"technical": 0.25, "leadership": 0.15}}
        cfg_b = {"weights": {"leadership": 0.15, "technical": 0.25}}
        self.assertEqual(
            self.mod.cache_key("ws1", "resume", job, cfg_a),
            self.mod.cache_key("ws1", "resume", job, cfg_b),
        )

    def test_resume_change_invalidates_key(self) -> None:
        job = {"url": "https://x/a", "description": "build APIs"}
        cfg = {"w": 1}
        self.assertNotEqual(
            self.mod.cache_key("ws", "resume v1", job, cfg),
            self.mod.cache_key("ws", "resume v2", job, cfg),
        )

    def test_description_change_invalidates_key(self) -> None:
        cfg = {"w": 1}
        a = {"url": "https://x/a", "description": "build APIs"}
        b = {"url": "https://x/a", "description": "build APIs and tests"}
        self.assertNotEqual(
            self.mod.cache_key("ws", "r", a, cfg),
            self.mod.cache_key("ws", "r", b, cfg),
        )

    def test_weights_change_invalidates_key(self) -> None:
        job = {"url": "https://x/a", "description": "x"}
        self.assertNotEqual(
            self.mod.cache_key("ws", "r", job, {"w": 1}),
            self.mod.cache_key("ws", "r", job, {"w": 2}),
        )

    def test_workspace_change_invalidates_key(self) -> None:
        job = {"url": "https://x/a", "description": "x"}
        self.assertNotEqual(
            self.mod.cache_key("ws1", "r", job, {}),
            self.mod.cache_key("ws2", "r", job, {}),
        )


class ScoreCachePersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = importlib.import_module("job_finder.scoring.score_cache")
        # Redirect cache dir to a tmp location per test.
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = patch.object(
            self.mod, "_CACHE_DIR", Path(self._tmp.name) / "ai_scores",
        )
        self._patch.start()
        # Ensure env-var disable isn't leaking in from the host shell.
        os.environ.pop("LAUNCHBOARD_DISABLE_AI_SCORE_CACHE", None)

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_save_then_load_roundtrip(self) -> None:
        score = {"overall_score": 78, "recommendation": "APPLY"}
        self.mod.save_cached("key123", score)
        loaded = self.mod.load_cached("key123")
        self.assertEqual(loaded, score)

    def test_load_missing_returns_none(self) -> None:
        self.assertIsNone(self.mod.load_cached("nonexistent"))

    def test_save_skips_empty_input(self) -> None:
        self.mod.save_cached("k", {})
        self.assertIsNone(self.mod.load_cached("k"))

    def test_save_skips_non_dict_input(self) -> None:
        self.mod.save_cached("k", "not a dict")  # type: ignore[arg-type]
        self.assertIsNone(self.mod.load_cached("k"))

    def test_load_returns_none_for_expired_entry(self) -> None:
        # Write a payload with an old cached_at.
        cache_dir = self.mod._CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / "expired.json"
        stale = datetime.now(timezone.utc) - timedelta(days=self.mod.CACHE_TTL_DAYS + 1)
        path.write_text(json.dumps({
            "version": 1,
            "cached_at": stale.isoformat(),
            "score": {"overall_score": 50},
        }))
        self.assertIsNone(self.mod.load_cached("expired"))

    def test_load_returns_none_for_corrupt_file(self) -> None:
        cache_dir = self.mod._CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "bad.json").write_text("{not valid json")
        self.assertIsNone(self.mod.load_cached("bad"))

    def test_env_kill_switch_blocks_both_read_and_write(self) -> None:
        os.environ["LAUNCHBOARD_DISABLE_AI_SCORE_CACHE"] = "1"
        try:
            self.mod.save_cached("kdisabled", {"overall_score": 80})
            # Even though save was attempted, the kill switch blocked it
            # AND blocks subsequent reads.
            self.assertIsNone(self.mod.load_cached("kdisabled"))
        finally:
            os.environ.pop("LAUNCHBOARD_DISABLE_AI_SCORE_CACHE", None)


if __name__ == "__main__":
    unittest.main()
