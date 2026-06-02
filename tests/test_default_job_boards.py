"""LA-local coverage needs more than LinkedIn.

The default JobSpy board list was empty, and the UI only exposes a LinkedIn
toggle — so a user's only local-jobs board was LinkedIn, which rate-limits
after a handful of queries. Indeed (verified live: returns LA-metro listings —
El Segundo, Santa Monica, Long Beach, Hawthorne) is now in the default board
set. Glassdoor is intentionally NOT added: it returns HTTP 400 "location not
parsed" for "City, ST" inputs, so it would fail every run. The per-board
circuit breaker still skips Indeed if it CAPTCHA-walls, so this can't make a
run worse than LinkedIn-only.
"""
from __future__ import annotations

from app.schemas.workspace import WorkspacePreferences
from app.services.workspace_service import (
    _DEFAULT_JOBSPY_BOARDS,
    build_pipeline_config_override,
)


def test_default_boards_include_indeed():
    assert "indeed" in _DEFAULT_JOBSPY_BOARDS


def test_config_override_searches_indeed_without_linkedin():
    prefs = WorkspacePreferences(include_linkedin_jobs=False)
    boards = build_pipeline_config_override(prefs, "ws1")["job_boards"]
    assert "indeed" in boards
    assert "linkedin" not in boards


def test_config_override_adds_linkedin_when_enabled():
    prefs = WorkspacePreferences(include_linkedin_jobs=True)
    boards = build_pipeline_config_override(prefs, "ws1")["job_boards"]
    assert "linkedin" in boards
    assert "indeed" in boards
