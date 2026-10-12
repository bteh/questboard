"""YC-backed companies get tagged as startups by their job board.

Real case, Oct 12 2026: Brian said "I don't have a lot of startup companies".
The "Startups & founding" chip showed 204 companies while 90% of Find Work
rows were company_type "Unknown": headcount was never filled and funding
stage only for ~3%. TRM Labs, Hightouch and Deepgram sat on the board as
Unknown although they are YC companies hiring on their own Ashby/Greenhouse
boards. The search-only save path also dropped funding_stage entirely.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from job_finder import startup_boards
from job_finder.company_classifier import classify_company
from job_finder.company_signals import fill_funding_from_text

_SNAPSHOT = {
    ("ashby", "trmlabs"): {"name": "TRM Labs", "stage": "Early", "batch": "Winter 2019"},
    ("greenhouse", "hightouch"): {"name": "Hightouch", "stage": "Growth", "batch": "Summer 2019"},
    ("lever", "curri"): {"name": "Curri", "stage": "Growth", "batch": "Summer 2019"},
}


@pytest.fixture
def snapshot(monkeypatch):
    monkeypatch.setattr(startup_boards, "_boards", lambda: _SNAPSHOT)
    monkeypatch.setattr(startup_boards, "snapshot_version", lambda: 20261012)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://jobs.ashbyhq.com/trmlabs/6ef44caf-1", ("ashby", "trmlabs")),
        ("https://jobs.ashbyhq.com/TRMLabs", ("ashby", "trmlabs")),
        ("https://boards.greenhouse.io/hightouch/jobs/123", ("greenhouse", "hightouch")),
        ("https://job-boards.greenhouse.io/hightouch/jobs/123", ("greenhouse", "hightouch")),
        ("https://boards.greenhouse.io/embed/job_app?for=hightouch&token=1", ("greenhouse", "hightouch")),
        ("https://jobs.lever.co/curri/abc-123", ("lever", "curri")),
        ("https://www.linkedin.com/jobs/view/123", None),
        ("", None),
        (None, None),
    ],
)
def test_board_for_url(url, expected):
    assert startup_boards.board_for_url(url) == expected


def test_yc_board_reads_as_a_startup_stage(snapshot):
    assert startup_boards.startup_stage_for_url(
        "https://jobs.ashbyhq.com/trmlabs/1"
    ) == "YC W19 (early)"
    assert startup_boards.startup_stage_for_url(
        "https://boards.greenhouse.io/hightouch/jobs/2"
    ) == "YC S19 (growth)"
    assert startup_boards.startup_stage_for_url("https://jobs.ashbyhq.com/dave/1") is None


def test_yc_stage_classifies_into_startup_tiers():
    assert classify_company("TRM Labs", funding_stage="YC W19 (early)") == "Early Startup"
    assert classify_company("Hightouch", funding_stage="YC S19 (growth)") == "Growth Stage"


def test_known_list_still_wins_over_yc_stage():
    # Stripe is a YC company; the curated list already calls it Elite Startup.
    assert classify_company("Stripe", funding_stage="YC S09 (growth)") == "Elite Startup"


def test_fill_funding_reads_the_job_board(snapshot):
    job = {"company": "Trm Labs", "url": "https://jobs.ashbyhq.com/trmlabs/1", "description": ""}
    fill_funding_from_text(job)
    assert job["funding_stage"] == "YC W19 (early)"


def test_fill_funding_keeps_a_stated_round(snapshot):
    job = {
        "company": "Trm Labs",
        "url": "https://jobs.ashbyhq.com/trmlabs/1",
        "funding_stage": "Series B",
    }
    fill_funding_from_text(job)
    assert job["funding_stage"] == "Series B"


def test_bundled_snapshot_loads_and_is_well_formed():
    boards = startup_boards._boards()
    assert boards, "config/startup_boards.json must ship with the app"
    for (ats, slug), fact in boards.items():
        assert ats in {"ashby", "greenhouse", "lever"}
        assert slug == slug.lower()
        assert fact["stage"] in {"Early", "Growth"}


def test_search_only_save_keeps_funding_and_startup_tier(tmp_path, monkeypatch, snapshot):
    """The desktop Run search path saved neither funding_stage nor a startup tier."""
    db_file = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    from job_finder.models import database

    database.init_db(str(db_file))
    try:
        from app.services.pipeline_service import _save_search_results

        _save_search_results(
            SimpleNamespace(profile_name="default"),
            [{
                "title": "Data Engineer",
                "company": "Trm Labs",
                "url": "https://jobs.ashbyhq.com/trmlabs/abc",
                "source": "ashby",
                "description": "Build data pipelines.",
            }],
            lambda msg: None,
        )
        rec = database.get_all_applications()[0]
        assert rec.funding_stage == "YC W19 (early)"
        assert rec.company_type == "Early Startup"
    finally:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()


def test_repair_tags_stored_rows_once(tmp_path, monkeypatch, snapshot):
    from sqlalchemy import create_engine, text

    from job_finder.models.startup_board_repair import repair_startup_boards

    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications (id INTEGER PRIMARY KEY, company TEXT, job_url TEXT, "
            "company_type TEXT, funding_stage TEXT, total_funding TEXT, vertical TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO applications VALUES "
            "(1, 'Trm Labs', 'https://jobs.ashbyhq.com/trmlabs/1', 'Unknown', '', '', 'career'),"
            "(2, 'Hightouch', 'https://boards.greenhouse.io/hightouch/jobs/2', 'Growth Stage', NULL, NULL, 'career'),"
            "(3, 'Dave', 'https://jobs.ashbyhq.com/dave/3', 'Unknown', '', '', 'career'),"
            "(4, 'Curri', 'https://jobs.lever.co/curri/4', 'Unknown', 'Series C', '', 'career'),"
            "(5, 'Trm Labs', 'https://jobs.ashbyhq.com/trmlabs/5', 'Unknown', '', '', 'perform')"
        ))

    assert repair_startup_boards(engine) == 2
    with engine.connect() as conn:
        rows = dict(
            (r[0], (r[1], r[2]))
            for r in conn.execute(text("SELECT id, company_type, funding_stage FROM applications"))
        )
    assert rows[1] == ("Early Startup", "YC W19 (early)")
    assert rows[2] == ("Growth Stage", "YC S19 (growth)")
    assert rows[3] == ("Unknown", "")
    assert rows[4] == ("Unknown", "Series C")  # a stated round is never overwritten
    assert rows[5] == ("Unknown", "")  # side quests are not employers
    assert repair_startup_boards(engine) == 0


# ---------------------------------------------------------------------------
# Supply: YC boards rotate on their own lane
# ---------------------------------------------------------------------------
# 1,484 YC companies were hiring on Oct 12 2026 and 187 of the boards found
# for them sat in no catalog. The general catalog rotation needs ~21 pulls to
# reach every Ashby board, so YC boards get their own, shorter cycle.


@pytest.fixture
def ats_discovery(monkeypatch, tmp_path):
    import importlib

    mod = importlib.import_module("job_finder.tools.scrapers._ats_discovery")
    monkeypatch.setattr(mod, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.delenv("QUESTBOARD_DISABLE_ATS_CATALOG_ROTATION", raising=False)
    return mod


def test_startup_lane_walks_every_yc_board_for_its_host(ats_discovery, monkeypatch):
    from datetime import datetime, timedelta, timezone

    fake = {("ashby", f"yc-{i:02d}"): {"stage": "Early"} for i in range(10)}
    fake[("lever", "curri")] = {"stage": "Growth"}
    monkeypatch.setattr(startup_boards, "_boards", lambda: fake)

    t0 = datetime(2026, 10, 12, 9, tzinfo=timezone.utc)
    seen: set[str] = set()
    for pull in range(3):
        seen |= ats_discovery.startup_rotation_slugs(
            "ashby", batch_size=4, at=t0 + timedelta(hours=3 * pull),
        )
    assert seen == {f"yc-{i:02d}" for i in range(10)}
    assert ats_discovery.startup_rotation_slugs("lever", batch_size=4, at=t0) == {"curri"}


def test_startup_lane_respects_the_rotation_kill_switch(ats_discovery, monkeypatch):
    monkeypatch.setattr(startup_boards, "_boards", lambda: {("ashby", "x"): {}})
    monkeypatch.setenv("QUESTBOARD_DISABLE_ATS_CATALOG_ROTATION", "1")
    assert ats_discovery.startup_rotation_slugs("ashby") == set()


def test_bundled_snapshot_covers_the_motivating_companies():
    boards = startup_boards._boards()
    assert ("ashby", "trm-labs") in boards
    assert ("ashby", "hightouch") in boards
    assert ("ashby", "deepgram") in boards
    # Generic names a YC company shares with an unrelated board stay out.
    names = {fact["name"] for fact in boards.values()}
    assert "Medium Biosciences" not in names


def test_sidecar_bundles_the_snapshot(tmp_path, monkeypatch):
    """The installed app reads the snapshot from job_finder/config."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import build_desktop_sidecar

    staging = tmp_path / "tauri-sidecars"
    staging.mkdir()
    monkeypatch.setattr(build_desktop_sidecar, "sidecar_dir", lambda: staging)
    monkeypatch.setattr(build_desktop_sidecar, "pyinstaller_work_dir", lambda: tmp_path / "work")
    seen: list[list[str]] = []

    def fake_run(command, **kwargs):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, stdout="6.0\n", stderr="")
        seen.append(list(command))
        (staging / build_desktop_sidecar.sidecar_name()).write_bytes(b"built")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(build_desktop_sidecar.subprocess, "run", fake_run)
    build_desktop_sidecar.build_sidecar()

    expected = f"{startup_boards.SNAPSHOT_PATH}{os.pathsep}job_finder/config"
    assert any(expected in cmd for cmd in seen)
