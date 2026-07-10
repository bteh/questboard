"""The run-log and health endpoints behind the /health ops page.

Triage is two calls: GET /scrapers/health for worst-first verdicts, then
GET /scrapers/runs (optionally ?source=) for the raw rows behind a verdict.
These tests seed the scrape_runs table through the same code path the
scrapers use and read it back through the API.
"""

from __future__ import annotations

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


def _seed_runs(jf_db) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    jf_db.record_scrape_runs(
        [
            # steady source: healthy yesterday, healthy now
            {"source": "remotive", "vertical": "career", "started_at": now - timedelta(days=1),
             "duration_s": 3.0, "finish_reason": "ok", "rows_found": 30},
            {"source": "remotive", "vertical": "career", "started_at": now,
             "duration_s": 2.5, "finish_reason": "ok", "rows_found": 28},
            # broken source: raised on the latest run
            {"source": "sittercity", "vertical": "lookafter", "started_at": now - timedelta(hours=1),
             "duration_s": 12.0, "finish_reason": "exception", "rows_found": 0,
             "error_sample": "HTTP 429 from city page"},
        ]
    )


def test_runs_come_back_newest_first(api_client) -> None:
    client, jf_db = api_client
    _seed_runs(jf_db)

    resp = client.get("/api/v1/scrapers/runs")
    assert resp.status_code == 200, resp.text
    runs = resp.json()["runs"]
    assert len(runs) == 3
    assert runs[0]["source"] == "remotive"
    assert runs[0]["rows_found"] == 28
    assert runs[1]["source"] == "sittercity"
    assert runs[1]["finish_reason"] == "exception"
    assert runs[1]["error_sample"] == "HTTP 429 from city page"


def test_source_filter_narrows_to_one_source(api_client) -> None:
    client, jf_db = api_client
    _seed_runs(jf_db)

    resp = client.get("/api/v1/scrapers/runs", params={"source": "remotive"})
    runs = resp.json()["runs"]
    assert {r["source"] for r in runs} == {"remotive"}
    assert len(runs) == 2


def test_limit_caps_the_rows(api_client) -> None:
    client, jf_db = api_client
    _seed_runs(jf_db)

    resp = client.get("/api/v1/scrapers/runs", params={"limit": 1})
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["rows_found"] == 28  # newest survives the cap


def test_runs_carry_registry_display_names(api_client) -> None:
    client, jf_db = api_client
    _seed_runs(jf_db)

    resp = client.get("/api/v1/scrapers/runs", params={"source": "remotive"})
    assert resp.json()["runs"][0]["display_name"] == "Remotive"


def test_health_endpoint_ranks_worst_first(api_client) -> None:
    client, jf_db = api_client
    _seed_runs(jf_db)

    resp = client.get("/api/v1/scrapers/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["needs_attention"] == 1
    verdicts = {s["source"]: s["verdict"] for s in body["sources"]}
    assert verdicts["sittercity"] == "failing"
    assert verdicts["remotive"] == "ok"
    assert body["sources"][0]["source"] == "sittercity"


def test_empty_log_returns_empty_lists(api_client) -> None:
    client, _jf_db = api_client
    assert client.get("/api/v1/scrapers/runs").json() == {"runs": []}
    health = client.get("/api/v1/scrapers/health").json()
    assert health == {"sources": [], "needs_attention": 0}
