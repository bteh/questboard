"""Pytest fixtures for the questboard test suite.

Centralises test isolation so individual modules don't have to worry about
side-effects bleeding between runs (e.g. on-disk caches).
"""
from __future__ import annotations

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
