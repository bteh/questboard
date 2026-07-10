"""Local mode owns ONE data pool.

In local (non-hosted) mode the frontend still bootstraps a workspace
session (for CSRF and the future desktop mode), which sets the lb_session
cookie. Data reads and writes must NOT scope to that anonymous workspace:
the pipeline and CLI write rows with workspace_id NULL, so a scoped read
sees nothing and the whole app blanks from the second page load onward
(the board says "0 live" for every returning visitor). Workspace scoping
is hosted-mode behavior only.
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
    )
    jf_db.save_application(
        job_title="Snack focus group",
        company="Fieldwork",
        job_url="https://example.com/quests/snack",
        vertical="study",
    )


def _bootstrap(client) -> None:
    resp = client.post("/api/v1/session/bootstrap")
    assert resp.status_code == 200, resp.text
    assert "lb_session" in client.cookies


def test_board_summary_survives_a_session_cookie(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    before = client.get("/api/v1/board/summary").json()
    assert before["total"] == 2

    _bootstrap(client)

    after = client.get("/api/v1/board/summary").json()
    assert after["total"] == 2, (
        "a local session cookie must not hide the local data pool"
    )


def test_application_list_survives_a_session_cookie(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)
    _bootstrap(client)

    resp = client.get("/api/v1/applications", params={"vertical": "career,study"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 2


def test_workspace_scope_id_scopes_rows_only_in_hosted_mode(api_client, monkeypatch) -> None:
    from app.dependencies import workspace_scope_id

    class _Ws:
        id = "ws-123"

    class _Ctx:
        workspace = _Ws()

    assert workspace_scope_id(None) is None
    assert workspace_scope_id(_Ctx()) is None, "local: identity only, never row scope"

    monkeypatch.setenv("HOSTED_MODE", "true")
    assert workspace_scope_id(_Ctx()) == "ws-123"


def test_status_update_reaches_the_pool_with_a_session_cookie(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)
    _bootstrap(client)

    listed = client.get("/api/v1/applications", params={"vertical": "career"}).json()
    assert listed["total"] == 1
    app_id = listed["items"][0]["id"]

    resp = client.patch(f"/api/v1/applications/{app_id}/status", json={"status": "clipped"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "clipped"
