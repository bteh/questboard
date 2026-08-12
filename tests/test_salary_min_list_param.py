"""The /applications list endpoint takes a salary_min annual floor.

The board UI lets the user type a pay floor ("150k"). The filter must mirror
job_finder.pipeline._job_salary_passes, the same semantics the search-time
salary filter (test_salary_filter_parsed.py) exercises: prefer the annualized
columns, use the range midpoint when both ends are stated, and keep rows with
no salary data at all.
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
        job_title="Above the floor",
        company="Acme",
        job_url="https://example.com/jobs/above",
        salary_min=160000.0,
        salary_max=190000.0,
    )
    jf_db.save_application(
        job_title="Below the floor",
        company="Acme",
        job_url="https://example.com/jobs/below",
        salary_min=55000.0,
        salary_max=65000.0,
    )
    jf_db.save_application(
        job_title="No pay stated",
        company="Acme",
        job_url="https://example.com/jobs/unknown",
    )
    # Hourly posting: the raw numbers would never clear an annual floor, so
    # the filter must read the annualized columns first.
    jf_db.save_application(
        job_title="Hourly above the floor",
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


def test_no_floor_returns_everything(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 4


def test_floor_drops_stated_pay_below_it(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_min": 150000})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["total"] == 3
    assert _titles(payload) == {
        "Above the floor",
        "No pay stated",
        "Hourly above the floor",
    }


def test_floor_uses_midpoint_of_stated_range(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # 160k to 190k has a midpoint of 175k: in at 175k, out at 176k.
    resp = client.get("/api/v1/applications", params={"salary_min": 175000})
    assert "Above the floor" in _titles(resp.json())

    resp = client.get("/api/v1/applications", params={"salary_min": 176000})
    assert "Above the floor" not in _titles(resp.json())


def test_floor_keeps_rows_with_no_pay_data(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_min": 500000})
    payload = resp.json()
    assert payload["total"] == 1
    assert _titles(payload) == {"No pay stated"}


def test_floor_only_compares_rows_in_the_requested_currency(api_client) -> None:
    client, jf_db = api_client
    jf_db.save_application(
        job_title="Low USD",
        company="Acme",
        job_url="https://example.com/jobs/low-usd",
        salary_min=90_000,
        salary_max=90_000,
        salary_currency="USD",
    )
    jf_db.save_application(
        job_title="EUR not comparable",
        company="Acme",
        job_url="https://example.com/jobs/eur",
        salary_min=90_000,
        salary_max=90_000,
        salary_currency="EUR",
    )
    jf_db.save_application(
        job_title="Currency missing",
        company="Acme",
        job_url="https://example.com/jobs/currency-missing",
        salary_min=90_000,
        salary_max=90_000,
    )

    resp = client.get(
        "/api/v1/applications",
        params={"salary_min": 120_000, "salary_currency": "USD"},
    )
    assert resp.status_code == 200, resp.text
    assert _titles(resp.json()) == {"EUR not comparable", "Currency missing"}


def test_negative_floor_rejected(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_min": -1})
    assert resp.status_code == 422
