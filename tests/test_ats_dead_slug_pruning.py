"""Slug discovery must forget boards that do not exist, and only those.

Slug discovery harvests company names out of DuckDuckGo results, so some of
what it caches never had a board on that host. Measured 2026-07-27: ~40 of
Lever's and ~33 of Ashby's cached slugs answered 404 on every single pull,
each one costing a request and a slow failure, forever, because nothing ever
removed them.

The dangerous half of this is the opposite mistake. Ashby was refusing
connections in bulk that same day ([Errno 61]); if a refused board counted as
dead, one bad minute would have erased hundreds of real companies from the
cache. Only a definite 404 prunes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import _ats_discovery  # noqa: E402
from job_finder.tools.scrapers._ats_discovery import DeadBoards, drop_slugs  # noqa: E402


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(_ats_discovery, "_CACHE_DIR", tmp_path)
    return tmp_path


def _write_cache(cache_dir, host, slugs, discovered_at=None):
    path = cache_dir / f"ats_discovered_{host}.json"
    path.write_text(json.dumps({
        "version": 1,
        "host": host,
        "discovered_at": discovered_at or datetime.now(timezone.utc).isoformat(),
        "slugs": sorted(slugs),
    }))
    return path


def _read_cache(cache_dir, host):
    return json.loads((cache_dir / f"ats_discovered_{host}.json").read_text())


def test_a_404_board_is_dropped_from_the_cache(cache_dir):
    _write_cache(cache_dir, "lever", ["realco", "ghostco", "otherco"])

    dead = DeadBoards("lever")
    dead.watch("ghostco")(404)
    assert dead.prune() == 1

    assert _read_cache(cache_dir, "lever")["slugs"] == ["otherco", "realco"]


def test_a_refused_board_is_kept(cache_dir):
    """The Ashby failure mode: a transport error reports no status at all."""
    _write_cache(cache_dir, "ashby", ["realco", "flakyco"])

    dead = DeadBoards("ashby")
    dead.watch("flakyco")(None)  # connection refused, timeout, DNS
    assert dead.prune() == 0

    assert _read_cache(cache_dir, "ashby")["slugs"] == ["flakyco", "realco"]


def test_a_rate_limited_board_is_kept(cache_dir):
    """Workable answers 429 in bulk under load. Those are live companies."""
    _write_cache(cache_dir, "workable", ["realco", "busyco"])

    dead = DeadBoards("workable")
    dead.watch("busyco")(429)
    assert dead.prune() == 0
    assert _read_cache(cache_dir, "workable")["slugs"] == ["busyco", "realco"]


def test_a_healthy_board_is_kept(cache_dir):
    _write_cache(cache_dir, "lever", ["realco"])
    dead = DeadBoards("lever")
    dead.watch("realco")(200)
    assert dead.prune() == 0
    assert _read_cache(cache_dir, "lever")["slugs"] == ["realco"]


def test_pruning_does_not_look_like_a_refresh(cache_dir):
    """Rewriting discovered_at would reset the 7-day TTL and make every prune
    trigger a fresh DuckDuckGo sweep on the next run."""
    stamped = "2026-07-20T01:00:00+00:00"
    _write_cache(cache_dir, "lever", ["realco", "ghostco"], discovered_at=stamped)

    dead = DeadBoards("lever")
    dead.watch("ghostco")(404)
    dead.prune()

    assert _read_cache(cache_dir, "lever")["discovered_at"] == stamped


def test_pruning_a_missing_cache_is_a_no_op(cache_dir):
    assert drop_slugs("neverran", {"ghostco"}) == 0


def test_nothing_dead_means_no_write(cache_dir):
    path = _write_cache(cache_dir, "lever", ["realco"])
    before = path.stat().st_mtime_ns
    assert DeadBoards("lever").prune() == 0
    assert path.stat().st_mtime_ns == before


def test_watchers_are_thread_safe_across_a_fan_out(cache_dir):
    """Boards are fetched from a worker pool, so the set is written
    concurrently."""
    from concurrent.futures import ThreadPoolExecutor

    slugs = [f"ghost{i:03d}" for i in range(200)]
    _write_cache(cache_dir, "lever", [*slugs, "realco"])

    dead = DeadBoards("lever")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda s: dead.watch(s)(404), slugs))

    assert dead.prune() == 200
    assert _read_cache(cache_dir, "lever")["slugs"] == ["realco"]
