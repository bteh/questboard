"""The board restocks itself: cadence contracts, due logic, the sweep loop.

Cadence is a per-source registry declaration (refresh_hours), due-ness is
measured from the last ATTEMPT in the run log (a failing source retries at
its rhythm, never every tick), and the loop sweeps exactly the due sources
through run_quest_search. Tests never fire a real sweep.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

NOW = datetime(2026, 7, 10, 12, 0, 0)


class TestCadenceContract:
    def test_every_live_quest_source_declares_a_cadence(self) -> None:
        from job_finder.tools.scrapers import get_registry

        for name, meta in get_registry().items():
            if (
                meta.search_fn is None
                or meta.vertical == "career"
                or meta.research_only
            ):
                continue
            assert meta.refresh_hours, (
                f"{name} feeds the board but declares no refresh_hours; "
                "an un-refreshed source decays via its own expiry contract"
            )

    def test_career_and_research_sources_are_never_schedulable(self) -> None:
        from job_finder.schedule import schedulable_metas

        for meta in schedulable_metas():
            assert meta.vertical != "career"
            assert not meta.research_only
            assert meta.refresh_hours


class TestDueLogic:
    def _patch_registry(self, monkeypatch, metas) -> None:
        import job_finder.schedule as schedule

        monkeypatch.setattr(schedule, "schedulable_metas", lambda: metas)

    def _meta(self, name: str, hours: int, vertical: str = "house"):
        from job_finder.tools.scrapers._registry import ScraperMeta

        return ScraperMeta(
            name=name, display_name=name, url="", description="", category="",
            enabled_by_default=False, search_fn=lambda: [], vertical=vertical,
            refresh_hours=hours,
        )

    def test_never_ran_is_due_immediately(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(monkeypatch, [self._meta("fresh_source", 24)])
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts", lambda: {}
        )
        due = schedule.due_sources(NOW)
        assert [s.name for s in due] == ["fresh_source"]
        assert due[0].due_at is None

    def test_recent_attempt_is_not_due(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(monkeypatch, [self._meta("steady", 24)])
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts",
            lambda: {"steady": NOW - timedelta(hours=2)},
        )
        assert schedule.due_sources(NOW) == []

    def test_stale_attempt_is_due(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(monkeypatch, [self._meta("stale", 12)])
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts",
            lambda: {"stale": NOW - timedelta(hours=13)},
        )
        due = schedule.due_sources(NOW)
        assert [s.name for s in due] == ["stale"]
        assert due[0].due_at == NOW - timedelta(hours=1)

    def test_schedule_sorts_soonest_due_first(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(
            monkeypatch,
            [self._meta("later", 24), self._meta("never_ran", 24), self._meta("soon", 12)],
        )
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts",
            lambda: {
                "later": NOW - timedelta(hours=1),
                "soon": NOW - timedelta(hours=11),
            },
        )
        names = [s.name for s in schedule.board_schedule(NOW)]
        assert names == ["never_ran", "soon", "later"]


class TestOnlySources:
    def test_refresh_narrows_to_named_sources(self, monkeypatch) -> None:
        from job_finder import quests

        captured: dict = {}

        def fake_run_scrapers(names, **kw):
            captured["names"] = list(names)
            return []

        monkeypatch.setattr(quests, "run_scrapers", fake_run_scrapers)
        monkeypatch.setattr("job_finder.backup.snapshot_database", lambda **kw: None)

        summary = quests.run_quest_search(
            verticals=["house", "body"], only_sources=["bankrewards"]
        )
        assert captured["names"] == ["bankrewards"]
        assert list(summary["sources"]) == ["bankrewards"]

    def test_only_sources_cannot_smuggle_research_only(self, monkeypatch) -> None:
        from job_finder import quests

        captured: dict = {"names": []}

        def fake_run_scrapers(names, **kw):
            captured["names"] = list(names)
            return []

        monkeypatch.setattr(quests, "run_scrapers", fake_run_scrapers)
        monkeypatch.setattr("job_finder.backup.snapshot_database", lambda **kw: None)

        quests.run_quest_search(
            verticals=["odd", "flip"],
            only_sources=["reddit-slavelabour", "reddit-pkmntcgdeals"],
        )
        assert captured["names"] == []


class TestBoardScheduler:
    def _scheduler(self):
        from app.services.scheduler_service import BoardScheduler

        return BoardScheduler(tick_seconds=900, initial_delay_seconds=0)

    def test_tick_sweeps_exactly_the_due_sources(self, monkeypatch) -> None:
        import job_finder.schedule as schedule
        from job_finder.tools.scrapers._registry import ScraperMeta

        metas = [
            ScraperMeta(
                name="bankrewards", display_name="B", url="", description="",
                category="", enabled_by_default=False, search_fn=lambda: [],
                vertical="house", refresh_hours=24,
            )
        ]
        monkeypatch.setattr(schedule, "schedulable_metas", lambda: metas)
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts", lambda: {}
        )

        calls: list[dict] = []

        def fake_run_quest_search(**kw):
            calls.append(kw)
            return {"found": 3, "saved": 2, "expired": 0, "sources": {}}

        import job_finder.quests as quests

        monkeypatch.setattr(quests, "run_quest_search", fake_run_quest_search)

        sched = self._scheduler()
        swept = asyncio.run(sched.tick())
        assert swept == 1
        assert calls[0]["only_sources"] == ["bankrewards"]
        assert calls[0]["verticals"] == ["house"]
        assert calls[0]["workspace_id"] is None
        assert sched.sweeps_run == 1

    def test_tick_with_nothing_due_runs_nothing(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        monkeypatch.setattr(schedule, "due_sources", lambda now=None: [])

        import job_finder.quests as quests

        def boom(**kw):  # pragma: no cover - the assertion is that this never runs
            raise AssertionError("swept with nothing due")

        monkeypatch.setattr(quests, "run_quest_search", boom)
        sched = self._scheduler()
        assert asyncio.run(sched.tick()) == 0

    def test_build_scheduler_honors_kill_switch(self, monkeypatch) -> None:
        # get_settings constructs a fresh Settings per call, so env is enough
        from app.services import scheduler_service

        monkeypatch.setenv("SCHEDULER_ENABLED", "false")
        assert scheduler_service.build_scheduler() is None

        monkeypatch.setenv("SCHEDULER_ENABLED", "true")
        monkeypatch.setenv("HOSTED_MODE", "false")
        assert scheduler_service.build_scheduler() is not None

        # hosted runs the loop too: sweeps write the shared pool the
        # hosted board reads (one felt for every visitor)
        monkeypatch.setenv("HOSTED_MODE", "true")
        assert scheduler_service.build_scheduler() is not None


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("WORKSPACE_STORAGE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    for module_name in list(sys.modules):
        if (
            module_name == "app"
            or module_name.startswith("app.")
            or module_name == "job_finder.models"
            or module_name.startswith("job_finder.models.")
        ):
            sys.modules.pop(module_name, None)

    backend_db = importlib.import_module("app.models.database")
    backend_db.init_db(str(db_path))
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(db_path))
    app_main = importlib.import_module("app.main")

    with TestClient(app_main.app) as client:
        yield client, jf_db, app_main
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def test_schedule_endpoint_reports_due_state(api_client) -> None:
    client, jf_db, app_main = api_client
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    jf_db.record_scrape_runs(
        [
            {"source": "bankrewards", "vertical": "house",
             "started_at": now - timedelta(hours=1), "finish_reason": "ok", "rows_found": 80},
            {"source": "doctorofcredit", "vertical": "house",
             "started_at": now - timedelta(hours=20), "finish_reason": "ok", "rows_found": 50},
        ]
    )

    resp = client.get("/api/v1/scrapers/schedule")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # the suite-wide guard disables the loop; the schedule itself still reads
    assert body["scheduler_running"] is False
    entries = {s["source"]: s for s in body["sources"]}
    assert entries["bankrewards"]["due_now"] is False
    # 20h old attempt on a 12h cadence: overdue
    assert entries["doctorofcredit"]["due_now"] is True
    # never-ran sources are due immediately with no due_at
    assert entries["clinicaltrials"]["due_now"] is True
    assert entries["clinicaltrials"]["due_at"] is None
    # research-only sources never appear
    assert "reddit-pkmntcgdeals" not in entries


def test_lifespan_does_not_start_scheduler_when_disabled(api_client) -> None:
    client, _jf_db, app_main = api_client
    assert app_main.app.state.scheduler is None
