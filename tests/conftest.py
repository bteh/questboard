"""Pytest fixtures for the questboard test suite.

Centralises test isolation so individual modules don't have to worry about
side-effects bleeding between runs (e.g. on-disk caches).
"""
from __future__ import annotations


import sys
from pathlib import Path

# Tests import repo-level packages ("scripts.x", "tests.y") by name. Under
# `python -m pytest` the cwd is on sys.path so this works by accident; under
# bare `pytest` (CI) it only works if an earlier test happened to insert it.
# Put the repo root first so import order never decides a test's fate.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import os

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Point JOB_FINDER_DATA_DIR at a per-test temp directory.

    Several library code paths persist artifacts to the data dir:
    - ``expand_roles_with_ai`` writes ``expanded_roles_<profile>_<hash>.json``
    - SQLite tables when not using an explicit in-memory engine
    Without isolation, one test's cache can mask another's mocked LLM
    response and produce confusing failures.
    """
    monkeypatch.setenv("JOB_FINDER_DATA_DIR", str(tmp_path))
    yield
    # tmp_path is auto-cleaned by pytest; nothing further to do.


@pytest.fixture(autouse=True)
def _no_background_scheduler(monkeypatch):
    """No test may ever fire a real board sweep.

    The backend lifespan starts the board scheduler by default; a
    TestClient context would otherwise arm a loop that sweeps live
    sources. Scheduler tests opt back in explicitly.
    """
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
