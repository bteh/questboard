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

DeadBoards covers the slugs a pull actually fetched. It cannot reach a slug the
pull skipped, so entries only leave the cache as runs happen to touch them, and
Ashby still carried its dead ~33 days later. `sweep_dead_slugs` is the direct
pass: probe every cached slug once, prune what 404s, on demand rather than as a
side effect of searching for work.
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
from job_finder.tools.scrapers._ats_discovery import (  # noqa: E402
    DeadBoards,
    drop_slugs,
    sweep_dead_slugs,
)


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


# --- sweep_dead_slugs: the direct pass over everything already cached --------


def test_a_sweep_prunes_only_the_boards_that_answer_404(cache_dir):
    _write_cache(cache_dir, "ashby", ["realco", "ghostco", "otherco"])
    answers = {"realco": 200, "ghostco": 404, "otherco": 200}

    assert sweep_dead_slugs("ashby", answers.get) == 1
    assert _read_cache(cache_dir, "ashby")["slugs"] == ["otherco", "realco"]


def test_a_sweep_probes_every_cached_slug(cache_dir):
    """The whole point is reaching slugs a pull never got to."""
    slugs = [f"co{i:03d}" for i in range(50)]
    _write_cache(cache_dir, "ashby", slugs)
    seen: set[str] = set()

    def probe(slug: str) -> int:
        seen.add(slug)
        return 200

    sweep_dead_slugs("ashby", probe)
    assert seen == set(slugs)


def test_a_sweep_keeps_boards_it_could_not_reach(cache_dir):
    """Same rule as DeadBoards, and it matters more here: a sweep touches the
    whole cache at once, so treating a bad minute as death would empty it."""
    _write_cache(cache_dir, "ashby", ["realco", "flakyco", "busyco", "slowco"])

    answers = {"realco": 200, "flakyco": None, "busyco": 429, "slowco": 500}
    assert sweep_dead_slugs("ashby", answers.get) == 0
    assert _read_cache(cache_dir, "ashby")["slugs"] == [
        "busyco", "flakyco", "realco", "slowco",
    ]


def test_a_sweep_that_finds_everything_dead_refuses_to_empty_the_cache(cache_dir):
    """404 from every single board is a broken probe (wrong URL, DNS wildcard,
    captive portal), not 247 companies vanishing at once. Erasing the cache
    would cost a DuckDuckGo re-discovery of all of them."""
    slugs = [f"co{i:03d}" for i in range(20)]
    _write_cache(cache_dir, "ashby", slugs)

    assert sweep_dead_slugs("ashby", lambda _s: 404) == 0
    assert _read_cache(cache_dir, "ashby")["slugs"] == sorted(slugs)


def test_a_sweep_does_not_look_like_a_refresh(cache_dir):
    stamped = "2026-07-20T01:00:00+00:00"
    _write_cache(cache_dir, "ashby", ["realco", "ghostco"], discovered_at=stamped)

    sweep_dead_slugs("ashby", {"realco": 200, "ghostco": 404}.get)
    assert _read_cache(cache_dir, "ashby")["discovered_at"] == stamped


def test_a_sweep_of_a_missing_cache_is_a_no_op(cache_dir):
    assert sweep_dead_slugs("neverran", lambda _s: 404) == 0


def test_a_dry_sweep_writes_nothing(cache_dir):
    path = _write_cache(cache_dir, "ashby", ["realco", "ghostco"])
    before = path.stat().st_mtime_ns

    report = sweep_dead_slugs(
        "ashby", {"realco": 200, "ghostco": 404}.get, report=True, dry_run=True
    )
    assert report["dropped"] == 1
    assert path.stat().st_mtime_ns == before
    assert _read_cache(cache_dir, "ashby")["slugs"] == ["ghostco", "realco"]


def test_a_dry_sweep_names_what_it_would_drop(cache_dir):
    _write_cache(cache_dir, "ashby", ["realco", "ghostco"])
    report = sweep_dead_slugs(
        "ashby", {"realco": 200, "ghostco": 404}.get, report=True, dry_run=True
    )
    assert report["dead"] == ["ghostco"]


def test_a_dry_sweep_refuses_the_same_sweeps_a_real_one_would(cache_dir):
    """A preview that promises a prune the real run declines is worse than no
    preview: you would read "247 would be dropped", approve it, and watch
    nothing happen.
    """
    slugs = [f"co{i:03d}" for i in range(20)]
    _write_cache(cache_dir, "ashby", slugs)

    report = sweep_dead_slugs("ashby", lambda _s: 404, report=True, dry_run=True)
    assert report["dropped"] == 0
    assert report["dead"] == []


def test_a_sweep_reports_what_it_probed(cache_dir):
    """A caller printing "checked 247, dropped 33" needs both numbers, and a
    sweep that quietly probed 3 of 247 should be visible as that."""
    _write_cache(cache_dir, "ashby", ["realco", "ghostco"])

    result = sweep_dead_slugs("ashby", {"realco": 200, "ghostco": 404}.get, report=True)
    assert result["checked"] == 2
    assert result["dropped"] == 1
    assert result["unreachable"] == 0
