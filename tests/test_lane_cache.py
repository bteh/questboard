"""The browse_all lane cache must never serve a stale board.

The board's My Roles lane costs ~1s to build (every candidate through both
title gates plus shortlist scoring), so browse_all calls are cached. The
accuracy contract, each clause pinned here: any commit to the database from
ANY connection or process invalidates instantly (the stdio MCP server writing
fit judgments is a separate process, detected via PRAGMA data_version on a
held sentinel connection); a preference change invalidates; entries expire on
a TTL because rows age past the freshness window continuously; a served
payload is a copy, so callers cannot poison the cache; and the compact MCP
path never touches the cache at all.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


@pytest.fixture()
def lane_db(tmp_path, monkeypatch):
    import json

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    db.add(
        Workspace(
            id="configured",
            name="Configured",
            slug="configured",
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="configured",
            roles_json=json.dumps(["Data Engineering Manager"]),
            keywords_json=json.dumps(["data platform"]),
            workplace_preference="remote_friendly",
            max_days_old=45,
            current_level="manager",
        )
    )
    for n in range(3):
        db.add(
            ApplicationRecord(
                job_title=f"Data Engineering Manager {'I' * (n + 1)}",
                company=f"c{n}",
                job_url=f"https://x.example/{n}",
                vertical="career",
                date_found=now.replace(tzinfo=None) - timedelta(hours=n + 1),
                description="d",
            )
        )
    db.commit()

    from app.services import lane_cache

    lane_cache.clear()
    yield db, str(db_path)
    lane_cache.clear()
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


@pytest.fixture()
def build_counter(monkeypatch):
    from app.services import local_agent_service as svc

    calls = {"count": 0}
    real = svc._search_work_uncached

    def counted(*args, **kwargs):
        calls["count"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(svc, "_search_work_uncached", counted)
    return calls


def _lane(db):
    from app.services import local_agent_service as svc

    return svc.search_work(db, browse_all=True, use_saved_preferences=True)


def test_warm_serve_equals_cold_build_exactly(lane_db, build_counter) -> None:
    db, _ = lane_db
    cold = _lane(db)
    warm = _lane(db)
    assert warm == cold
    assert build_counter["count"] == 1, "the second call must come from cache"
    assert cold["total_matching"] == 3


def test_a_write_from_another_process_invalidates_immediately(
    lane_db, build_counter
) -> None:
    """The stdio MCP server writes fit judgments to the same SQLite file from
    its own process. A cached lane served after such a write would show the
    reader a board that ignores what their assistant just did."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from job_finder.models.database import ApplicationRecord

    db, db_path = lane_db
    assert _lane(db)["total_matching"] == 3

    other_engine = create_engine(f"sqlite:///{db_path}")
    with Session(other_engine) as other:
        other.add(
            ApplicationRecord(
                job_title="Data Engineering Manager IV",
                company="mcp",
                job_url="https://x.example/mcp",
                vertical="career",
                date_found=datetime.now(timezone.utc).replace(tzinfo=None),
                description="d",
            )
        )
        other.commit()
    other_engine.dispose()

    after = _lane(db)
    assert after["total_matching"] == 4, "the new row must appear immediately"
    assert build_counter["count"] == 2


def test_a_same_session_write_invalidates_too(lane_db, build_counter) -> None:
    from job_finder.models.database import ApplicationRecord

    db, _ = lane_db
    _lane(db)
    db.add(
        ApplicationRecord(
            job_title="Data Engineering Manager V",
            company="local",
            job_url="https://x.example/local",
            vertical="career",
            date_found=datetime.now(timezone.utc).replace(tzinfo=None),
            description="d",
        )
    )
    db.commit()
    assert _lane(db)["total_matching"] == 4
    assert build_counter["count"] == 2


def test_a_preference_change_invalidates(lane_db, build_counter) -> None:
    import json

    from app.models.workspace import WorkspacePreferences

    db, _ = lane_db
    assert _lane(db)["total_matching"] == 3
    prefs = db.query(WorkspacePreferences).one()
    prefs.roles_json = json.dumps(["Registered Nurse"])
    db.commit()
    assert _lane(db)["total_matching"] == 0
    assert build_counter["count"] == 2


def test_entries_expire_on_the_ttl(lane_db, build_counter, monkeypatch) -> None:
    """Rows age past the saved freshness window continuously, not at commits,
    so a quiet database must still rebuild once the TTL passes."""
    from app.services import lane_cache

    db, _ = lane_db
    _lane(db)
    monkeypatch.setattr(lane_cache, "_TTL_SECONDS", 0)
    _lane(db)
    assert build_counter["count"] == 2


def test_served_payload_mutation_cannot_poison_the_cache(lane_db) -> None:
    db, _ = lane_db
    first = _lane(db)
    first["results"].clear()
    first["total_matching"] = -99
    second = _lane(db)
    assert second["total_matching"] == 3
    assert len(second["results"]) == 3


def test_the_compact_mcp_path_never_touches_the_cache(lane_db, build_counter) -> None:
    from app.services import local_agent_service as svc

    db, _ = lane_db
    svc.search_work(db, browse_all=False, use_saved_preferences=True)
    svc.search_work(db, browse_all=False, use_saved_preferences=True)
    assert build_counter["count"] == 2, "non-browse_all always builds fresh"


def test_an_in_memory_database_bypasses_the_cache() -> None:
    """StaticPool in-memory engines share one connection, where data_version
    cannot see the process's own writes; caching there would serve stale
    boards in the exact setups tests use. The cache must refuse."""
    from app.services import lane_cache

    class FakeURL:
        database = ":memory:"

        @staticmethod
        def get_backend_name() -> str:
            return "sqlite"

    class FakeBind:
        url = FakeURL()

    class FakeSession:
        def get_bind(self):
            return FakeBind()

    builds = {"count": 0}

    def build():
        builds["count"] += 1
        return {"n": builds["count"]}

    assert lane_cache.get_or_build(FakeSession(), ("k",), build) == {"n": 1}
    assert lane_cache.get_or_build(FakeSession(), ("k",), build) == {"n": 2}
