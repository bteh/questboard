"""/board/summary: per-kind supply for the board rail.

Stored rows keep their historical vertical values; the endpoint maps them to
kinds via packages/kinds/kinds.json at read time. Dead URLs and the log's
personal lane never count. Kinds with zero supply still appear so the client
can render supply honesty instead of pretending the kind does not exist.
"""

from __future__ import annotations

import sys
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


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    import importlib

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
        yield client, jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def _seed(jf_db) -> None:
    jf_db.save_application(
        job_title="Senior Engineer",
        company="Acme",
        job_url="https://example.com/jobs/senior",
    )  # vertical defaults to career -> skill
    jf_db.save_application(
        job_title="Second shooter",
        company="r/forhire",
        job_url="https://example.com/quests/shooter",
        vertical="lens",
    )  # lens -> skill too
    jf_db.save_application(
        job_title="Snack focus group",
        company="Fieldwork",
        job_url="https://example.com/quests/snack",
        vertical="study",
    )  # study -> think
    jf_db.save_application(
        job_title="Background actor",
        company="Project Casting",
        job_url="https://example.com/quests/extra",
        vertical="camera",
    )  # camera -> perform


def _kind(payload: dict, kind_id: str) -> dict:
    return next(k for k in payload["kinds"] if k["id"] == kind_id)


def test_counts_map_legacy_verticals_onto_kinds(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/board/summary")
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["total"] == 4
    assert _kind(payload, "skill")["count"] == 2  # career + lens fold together
    assert _kind(payload, "think")["count"] == 1
    assert _kind(payload, "perform")["count"] == 1


def test_zero_supply_kinds_still_appear_for_supply_honesty(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = client.get("/api/v1/board/summary").json()
    ids = [k["id"] for k in payload["kinds"]]
    for expected in ("odd", "deliver", "lookafter", "flip", "house", "body", "party"):
        assert expected in ids
    assert _kind(payload, "deliver")["count"] == 0
    # ordered by the registry's display order
    orders = [k["order"] for k in payload["kinds"]]
    assert orders == sorted(orders)


def test_dead_personal_and_past_event_rows_never_count(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    session = jf_db._SessionLocal()
    try:
        from datetime import datetime, timedelta, timezone

        from job_finder.models.database import ApplicationRecord

        dead = ApplicationRecord(
            job_title="Gone listing",
            company="Ghost Co",
            job_url="https://example.com/jobs/gone",
            vertical="career",
            url_status="dead",
        )
        personal = ApplicationRecord(
            job_title="My own note",
            company="me",
            job_url="https://example.com/personal/note",
            vertical="personal",
        )
        past_taping = ApplicationRecord(
            job_title="Yesterday's audience seat",
            company="Studio",
            job_url="https://example.com/quests/past",
            vertical="camera",
            event_start=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2),
        )
        session.add_all([dead, personal, past_taping])
        session.commit()
    finally:
        session.close()

    payload = client.get("/api/v1/board/summary").json()
    assert payload["total"] == 4


def test_expired_tombstones_stay_off_the_board(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    session = jf_db._SessionLocal()
    try:
        from job_finder.models.database import ApplicationRecord

        row = session.query(ApplicationRecord).filter_by(vertical="study").first()
        row.url_status = "expired"
        session.commit()
    finally:
        session.close()

    payload = client.get("/api/v1/board/summary").json()
    assert payload["total"] == 3
    assert _kind(payload, "think")["count"] == 0


def test_fresh_rows_count_as_new_today(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = client.get("/api/v1/board/summary").json()
    # everything just seeded counts as new within 24h
    assert payload["new_today"] == payload["total"] == 4
    assert _kind(payload, "skill")["new_today"] == 2
