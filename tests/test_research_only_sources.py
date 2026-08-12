"""Reddit is research, not content: research_only sources never publish.

The 2026-07-10 curation audit found reddit-sourced rows breaking the
board's promise (bot drop announcements, a "[Removed by moderator]" title,
scam-shaped task posts). The debate verdict: reddit tells us WHERE to
crawl; it is never itself the content. The three reddit scrapers stay in
the tree as research tooling but are demoted to research_only, and no
selection path (career sweep or quest refresh) may ever run one.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

RESEARCH_ONLY_SOURCES = ("reddit-forhire", "reddit-slavelabour", "reddit-pkmntcgdeals")


@pytest.fixture()
def registry():
    from job_finder.tools.scrapers import get_registry

    return get_registry()


def test_reddit_sources_are_research_only(registry) -> None:
    for name in RESEARCH_ONLY_SOURCES:
        assert name in registry, f"{name} should stay registered as research tooling"
        assert registry[name].research_only is True, name


def test_career_sweep_never_selects_research_only(registry) -> None:
    _registry = importlib.import_module("job_finder.tools.scrapers._registry")
    defaults = _registry.default_scraper_names()
    for name, meta in registry.items():
        if getattr(meta, "research_only", False):
            assert name not in defaults, name


def test_quest_refresh_never_selects_research_only(monkeypatch) -> None:
    from job_finder import quests

    captured: dict = {}

    def fake_run_scrapers(names, **kw):
        captured["names"] = list(names)
        return []

    monkeypatch.setattr(quests, "run_scrapers", fake_run_scrapers)
    monkeypatch.setattr("job_finder.backup.snapshot_database", lambda **kw: None)

    from job_finder.kinds import known_vertical_values

    summary = quests.run_quest_search(verticals=sorted(known_vertical_values()))
    ran = captured.get("names", [])
    for name in RESEARCH_ONLY_SOURCES:
        assert name not in ran, f"{name} ran in a quest refresh"
        assert name not in summary["sources"], name
    # the refresh still runs real quest sources; the filter must not
    # accidentally empty the sweep
    assert ran, "quest refresh selected no sources at all"


def test_versioned_repair_tombstones_legacy_research_rows(tmp_path) -> None:
    from job_finder.models.maintenance import repair_research_only_rows

    engine = create_engine(f"sqlite:///{tmp_path / 'research.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            "id INTEGER PRIMARY KEY, source TEXT, url_status TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO applications (id, source, url_status) VALUES "
            "(1, 'doctorofcredit', 'unknown'), "
            "(2, 'scholarshipamerica', 'unknown')"
        ))

    assert repair_research_only_rows(engine) == 1
    with engine.begin() as conn:
        statuses = dict(conn.execute(text(
            "SELECT source, url_status FROM applications ORDER BY id"
        )).fetchall())
    assert statuses["doctorofcredit"] == "expired"
    assert statuses["scholarshipamerica"] == "unknown"
    assert repair_research_only_rows(engine) == 0
