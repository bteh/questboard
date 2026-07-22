"""The /applications list endpoint takes a salary_max annual ceiling.

The board UI has a "pay to" box, but the ceiling used to be trimmed
client-side over the loaded pages only, so the server total and the pager
kept counting rows the ceiling hid. The ceiling is a server param now,
mirroring salary_min: prefer annualized values, use the range midpoint when
both ends are stated, and KEEP rows with no salary data ("no pay stated" is
not "pays above your ceiling").
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
        job_title="Under the ceiling",
        company="Acme",
        job_url="https://example.com/jobs/under",
        salary_min=60000.0,
        salary_max=80000.0,
    )
    jf_db.save_application(
        job_title="Above the ceiling",
        company="Acme",
        job_url="https://example.com/jobs/over",
        salary_min=300000.0,
        salary_max=400000.0,
    )
    jf_db.save_application(
        job_title="No pay stated",
        company="Acme",
        job_url="https://example.com/jobs/unknown",
    )
    # Hourly posting whose raw numbers look tiny: the filter must read the
    # annualized columns first, exactly like the salary_min floor does.
    jf_db.save_application(
        job_title="Hourly above the ceiling",
        company="Acme",
        job_url="https://example.com/jobs/hourly",
        salary_min=80.0,
        salary_max=95.0,
        salary_period="hourly",
        salary_min_annualized=166400.0,
        salary_max_annualized=197600.0,
    )


def _titles(payload: dict) -> set[str]:
    return {item["job_title"] for item in payload["items"]}


def test_no_ceiling_returns_everything(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 4


def test_ceiling_drops_stated_pay_above_it(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_max": 150000})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    # the total is the SERVER's, so the pager can never promise rows the
    # ceiling hides
    assert payload["total"] == 2
    assert _titles(payload) == {"Under the ceiling", "No pay stated"}


def test_ceiling_uses_midpoint_of_stated_range(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # 60k to 80k has a midpoint of 70k: in at 70k, out at 69k.
    resp = client.get("/api/v1/applications", params={"salary_max": 70000})
    assert "Under the ceiling" in _titles(resp.json())

    resp = client.get("/api/v1/applications", params={"salary_max": 69000})
    assert "Under the ceiling" not in _titles(resp.json())


def test_ceiling_keeps_rows_with_no_pay_data(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_max": 1})
    payload = resp.json()
    assert payload["total"] == 1
    assert _titles(payload) == {"No pay stated"}


def test_floor_and_ceiling_combine(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"salary_min": 100000, "salary_max": 250000},
    )
    payload = resp.json()
    assert _titles(payload) == {"No pay stated", "Hourly above the ceiling"}


def test_negative_ceiling_rejected(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_max": -1})
    assert resp.status_code == 422
