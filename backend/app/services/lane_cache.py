"""Process-local cache for the board's ~1s browse_all lane build.

Accuracy contract (pinned by tests/test_lane_cache.py): a cached lane is
served only while ALL of these hold.

- Not one commit has landed on the SQLite file from ANY connection or
  process since the lane was built. Detection is PRAGMA data_version on a
  sentinel connection this module holds open per database file: SQLite bumps
  it for every other connection's commit, which covers the stdio MCP server
  writing fit judgments from its own process. The version is captured BEFORE
  building, so a write racing the build reads as stale next time, never as
  fresh.
- Every search argument and the fit profile hash match the cached key.
- The entry is younger than the TTL. Rows age past the saved freshness
  window continuously, not at commits, so a quiet database still drifts.

In-memory databases bypass the cache entirely: StaticPool shares one
connection, and data_version never sees a connection's own writes.
"""
from __future__ import annotations

import copy
import sqlite3
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

_TTL_SECONDS = 300
_MAX_ENTRIES = 8

_lock = threading.Lock()
_entries: "OrderedDict[tuple, tuple[float, int, dict[str, Any]]]" = OrderedDict()
_sentinels: dict[str, sqlite3.Connection] = {}


def _database_file(db: Any) -> str | None:
    try:
        url = db.get_bind().url
        if url.get_backend_name() != "sqlite":
            return None
        database = url.database
    except Exception:
        return None
    if not database or database == ":memory:":
        return None
    return str(database)


def _data_version(path: str) -> int | None:
    with _lock:
        sentinel = _sentinels.get(path)
        if sentinel is None:
            try:
                sentinel = sqlite3.connect(path, check_same_thread=False)
            except sqlite3.Error:
                return None
            _sentinels[path] = sentinel
        try:
            return int(sentinel.execute("PRAGMA data_version").fetchone()[0])
        except sqlite3.Error:
            _sentinels.pop(path, None)
            try:
                sentinel.close()
            except sqlite3.Error:
                pass
            return None


def get_or_build(
    db: Any, key: tuple, build: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    path = _database_file(db)
    version = _data_version(path) if path else None
    if version is None:
        return build()
    full_key = (path, key)
    now = time.monotonic()
    with _lock:
        hit = _entries.get(full_key)
        if hit is not None:
            built_at, built_version, payload = hit
            if built_version == version and now - built_at < _TTL_SECONDS:
                _entries.move_to_end(full_key)
                return copy.deepcopy(payload)
            del _entries[full_key]
    payload = build()
    with _lock:
        _entries[full_key] = (now, version, copy.deepcopy(payload))
        while len(_entries) > _MAX_ENTRIES:
            _entries.popitem(last=False)
    return payload


def clear() -> None:
    with _lock:
        _entries.clear()
        for sentinel in _sentinels.values():
            try:
                sentinel.close()
            except sqlite3.Error:
                pass
        _sentinels.clear()
