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

from pathlib import Path

from app.schemas.workspace import PlaceSelection, WorkspacePreferences
from app.services.workspace_service import (
    _DEFAULT_JOBSPY_BOARDS,
    build_pipeline_config_override,
)
from job_finder.tools.scrapers._utils import _load_seed_slugs


def test_default_boards_include_indeed():
    assert "indeed" in _DEFAULT_JOBSPY_BOARDS


def test_high_signal_primary_ats_boards_are_in_the_hot_seed_lane():
    data = Path(__file__).resolve().parents[1] / "src/job_finder/tools/scrapers/data"
    ashby = {
        line.strip().lower()
        for line in (data / "ashby_seed.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    greenhouse = {
        line.strip().lower()
        for line in (data / "greenhouse_seed.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {"confluent", "sentilink", "fabrion"} <= ashby
    assert {"yipitdata", "diligentrobotics"} <= greenhouse


def test_hot_seed_loader_leaves_bulk_catalog_to_daily_rotation():
    ashby = {slug.lower() for slug in _load_seed_slugs("ashby_seed.txt")}
    greenhouse = {slug.lower() for slug in _load_seed_slugs("greenhouse_seed.txt")}

    assert {"confluent", "sentilink", "fabrion"} <= ashby
    assert {"yipitdata", "diligentrobotics"} <= greenhouse
    assert "0g" not in ashby
    assert "103644278" not in greenhouse
    assert len(ashby) < 100
    assert len(greenhouse) < 150


def test_default_prefs_include_indeed_and_linkedin():
    """A second working board (LinkedIn) is on by default so one board
    tripping its circuit breaker can't black out the whole run."""
    boards = build_pipeline_config_override(WorkspacePreferences(), "ws1")["job_boards"]
    assert "indeed" in boards
    assert "linkedin" in boards


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


def test_config_override_uses_the_users_country_for_each_place():
    prefs = WorkspacePreferences(
        preferred_places=[
            PlaceSelection(
                label="London, United Kingdom",
                kind="city",
                match_scope="metro",
                city="London",
                country="United Kingdom",
                country_code="GB",
            ),
        ],
    )
    settings = build_pipeline_config_override(prefs, "ws1")["search_settings"]

    assert settings["country"] == "United Kingdom"
    assert settings["country_by_location"] == {
        "london, united kingdom": "United Kingdom",
    }
