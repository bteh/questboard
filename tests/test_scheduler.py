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


class TestCircuitBreaker:
    def _patch_registry(self, monkeypatch, metas) -> None:
        import job_finder.schedule as schedule

        monkeypatch.setattr(schedule, "schedulable_metas", lambda: metas)

    def _meta(self, name: str, hours: int = 12):
        from job_finder.tools.scrapers._registry import ScraperMeta

        return ScraperMeta(
            name=name, display_name=name, url="", description="", category="",
            enabled_by_default=False, search_fn=lambda: [], vertical="house",
            refresh_hours=hours,
        )

    def test_streak_counts_leading_failures_and_breaks_on_a_healthy_run(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        class _Run:
            def __init__(self, source, reason):
                self.source, self.finish_reason = source, reason

        # newest first: blocked has 3 leading failures then an ok; steady is clean
        runs = [
            _Run("blocked", "exception"), _Run("blocked", "timeout"),
            _Run("blocked", "exception"), _Run("blocked", "ok"),
            _Run("steady", "ok"), _Run("steady", "exception"),
        ]
        monkeypatch.setattr(
            "job_finder.models.database.get_recent_scrape_runs", lambda days=14: runs
        )
        streaks = schedule.failure_streaks()
        assert streaks == {"blocked": 3}  # steady's newest run is ok -> streak 0

    def test_a_source_under_threshold_keeps_normal_cadence(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(monkeypatch, [self._meta("wobbly", 12)])
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts",
            lambda: {"wobbly": NOW - timedelta(hours=13)},
        )
        monkeypatch.setattr(schedule, "failure_streaks", lambda: {"wobbly": 2})  # < threshold 3
        s = schedule.board_schedule(NOW)[0]
        assert s.breaker_open is False
        assert s.due(NOW) is True  # 13h old on a 12h cadence, still due

    def test_the_breaker_backs_a_failing_source_off(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(monkeypatch, [self._meta("blocked", 12)])
        last = NOW - timedelta(hours=13)  # normally due (past the 12h cadence)
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts",
            lambda: {"blocked": last},
        )
        monkeypatch.setattr(schedule, "failure_streaks", lambda: {"blocked": 3})
        s = schedule.board_schedule(NOW)[0]
        assert s.breaker_open is True
        assert s.failure_streak == 3
        # at the threshold the wait doubles the 12h cadence -> 24h
        assert s.due_at == last + timedelta(hours=24)
        # 13h since the last attempt but the breaker demands 24h: not due
        assert s.due(NOW) is False

    def test_backoff_doubles_the_cadence_and_caps(self) -> None:
        import job_finder.schedule as schedule

        # a 12h source: 2x, 4x, 8x, then capped at 72h
        assert schedule._breaker_backoff_hours(12, 3) == 24
        assert schedule._breaker_backoff_hours(12, 4) == 48
        assert schedule._breaker_backoff_hours(12, 5) == 72   # 96 capped to 72
        assert schedule._breaker_backoff_hours(12, 9) == 72
        # a 24h source doubles too
        assert schedule._breaker_backoff_hours(24, 3) == 48

    def test_a_deeply_failing_source_is_not_due(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        self._patch_registry(monkeypatch, [self._meta("hardblocked", 24)])
        last = NOW - timedelta(hours=40)  # long past its 24h cadence
        monkeypatch.setattr(
            "job_finder.models.database.latest_scrape_attempts",
            lambda: {"hardblocked": last},
        )
        monkeypatch.setattr(schedule, "failure_streaks", lambda: {"hardblocked": 4})  # 48h wait
        due = schedule.due_sources(NOW)
        # 40h since last attempt but the breaker demands 48h: not swept
        assert due == []


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

    def test_tick_reverifies_a_batch_of_links(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        monkeypatch.setattr(schedule, "due_sources", lambda now=None: [])

        captured: dict = {}

        def fake_check_urls(db, ids=None, limit=100, workspace_id=None, live_only=False):
            captured["limit"] = limit
            captured["live_only"] = live_only
            return {"checked": limit, "alive": limit, "dead": 0, "unknown": 0}

        from app.services import application_service

        monkeypatch.setattr(application_service, "check_urls", fake_check_urls)

        from app.services.scheduler_service import BoardScheduler

        sched = BoardScheduler(tick_seconds=900, initial_delay_seconds=0, reverify_batch=40)
        asyncio.run(sched.tick())
        assert captured == {"limit": 40, "live_only": True}

    def test_zero_batch_never_reverifies(self, monkeypatch) -> None:
        import job_finder.schedule as schedule

        monkeypatch.setattr(schedule, "due_sources", lambda now=None: [])

        from app.services import application_service

        def boom(*a, **kw):  # pragma: no cover - the assertion is that this never runs
            raise AssertionError("re-verified with a zero batch")

        monkeypatch.setattr(application_service, "check_urls", boom)
        sched = self._scheduler()  # reverify_batch defaults to 0
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
            {"source": "userinterviews", "vertical": "think",
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
    assert entries["userinterviews"]["due_now"] is True
    # never-ran sources are due immediately with no due_at
    assert entries["clinicaltrials"]["due_now"] is True
    assert entries["clinicaltrials"]["due_at"] is None
    # research-only sources never appear (doctorofcredit was demoted 2026-07-15)
    assert "reddit-pkmntcgdeals" not in entries
    assert "doctorofcredit" not in entries


def test_lifespan_does_not_start_scheduler_when_disabled(api_client) -> None:
    client, _jf_db, app_main = api_client
    assert app_main.app.state.scheduler is None


def test_reverify_skips_rows_already_off_the_board(api_client, monkeypatch) -> None:
    """live_only re-verification never wastes its batch on tombstones."""
    client, jf_db, app_main = api_client
    jf_db.save_application(
        job_title="Live row", company="X", job_url="https://x.example/live",
        vertical="house",
    )
    jf_db.save_application(
        job_title="Dead row", company="X", job_url="https://x.example/dead",
        vertical="house",
    )
    session = jf_db.get_session()
    try:
        dead = (
            session.query(jf_db.ApplicationRecord)
            .filter(jf_db.ApplicationRecord.job_url == "https://x.example/dead")
            .one()
        )
        dead.url_status = "dead"
        session.commit()
    finally:
        session.close()

    checked_urls: list[str] = []

    class _Resp:
        status_code = 200

    def fake_head(url, timeout=None, allow_redirects=None):
        checked_urls.append(url)
        return _Resp()

    monkeypatch.setattr("requests.head", fake_head)

    import importlib

    application_service = importlib.import_module("app.services.application_service")
    backend_db = importlib.import_module("app.models.database")
    db_gen = backend_db.get_db()
    db = next(db_gen)
    try:
        summary = application_service.check_urls(db, limit=10, live_only=True)
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass
    assert "https://x.example/live" in checked_urls
    assert "https://x.example/dead" not in checked_urls
    assert summary["checked"] == 1
