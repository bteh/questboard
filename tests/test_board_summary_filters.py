"""/board/summary honors the board's active filters.

The kind rail's badges and the "All quests" total read this endpoint; the
board list reads /applications with the user's filters. When the summary
ignored those filters the rail contradicted the board it sits above (a
search for "focus group" still showed hundreds under every kind). The
summary now takes the same filter params and applies the same shared
service predicates, so the two surfaces can never disagree.
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


def _seed(jf_db) -> None:
    now = datetime.now(timezone.utc)
    jf_db.save_application(
        job_title="Snack focus group",
        company="Fieldwork",
        job_url="https://example.com/quests/snack",
        location="Chicago, IL",
        vertical="study",  # -> think
        date_posted=(now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
        date_confidence="exact",
    )
    jf_db.save_application(
        job_title="LA babysitting",
        company="Sittercity",
        job_url="https://example.com/quests/sit",
        location="Culver City, CA",
        vertical="lookafter",
        salary_min=30.0,
        salary_max=30.0,
        salary_period="hourly",  # $62,400 a year at comparison time
        date_posted=(now - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%S"),
        date_confidence="exact",
    )
    jf_db.save_application(
        job_title="Nationwide bonus",
        company="DoC",
        job_url="https://example.com/quests/bonus",
        location="nationwide",
        vertical="house",
        salary_min=300.0,
        salary_max=300.0,
    )
    jf_db.save_application(
        job_title="No-experience mock jury",
        company="JuryTest",
        job_url="https://example.com/quests/jury",
        location="",
        vertical="study",  # -> think
        first_quest_ok=True,
    )


def _summary(client, **params) -> dict:
    resp = client.get("/api/v1/board/summary", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _kind(payload: dict, kind_id: str) -> dict:
    return next(k for k in payload["kinds"] if k["id"] == kind_id)


def test_unfiltered_summary_counts_everything(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = _summary(client)
    assert payload["total"] == 4
    assert _kind(payload, "think")["count"] == 2


def test_summary_honors_the_search_box(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = _summary(client, search="Snack")
    assert payload["total"] == 1
    assert _kind(payload, "think")["count"] == 1
    assert _kind(payload, "lookafter")["count"] == 0


def test_summary_honors_the_place_filter(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # same reachability rules as the list: the Chicago row matches, the
    # nationwide and placeless rows always pass, Culver City drops
    payload = _summary(client, location="Chicago")
    assert payload["total"] == 3
    assert _kind(payload, "lookafter")["count"] == 0

    strict = _summary(client, location="Chicago", location_strict="true")
    assert strict["total"] == 1
    assert _kind(strict, "think")["count"] == 1


def test_summary_honors_the_pay_floor_and_ceiling(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # floor 100k: the hourly $30 (=62.4k) and the $300 bonus drop; the two
    # no-pay rows stay, same keep-unknown rule as the list
    floor = _summary(client, salary_min=100000)
    assert floor["total"] == 2
    assert _kind(floor, "lookafter")["count"] == 0
    assert _kind(floor, "house")["count"] == 0

    # ceiling 500: the $300 bonus stays, the annualized hourly drops
    ceiling = _summary(client, salary_max=500)
    assert ceiling["total"] == 3
    assert _kind(ceiling, "house")["count"] == 1
    assert _kind(ceiling, "lookafter")["count"] == 0


def test_summary_honors_the_no_experience_preset(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = _summary(client, first_quest_ok="true")
    assert payload["total"] == 1
    assert _kind(payload, "think")["count"] == 1


def test_summary_honors_posted_within_days(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = _summary(client, posted_within_days=7)
    assert payload["total"] == 1
    assert _kind(payload, "think")["count"] == 1


def test_new_today_summary_and_list_share_the_local_calendar_predicate(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    params = {"found_within_days": 1, "timezone_name": "America/Los_Angeles"}
    summary = _summary(client, **params)
    listed = client.get(
        "/api/v1/applications",
        params={
            **params,
            "vertical": "career,study,lookafter,house",
            "scope": "board",
            "page_size": 100,
        },
    )
    assert listed.status_code == 200, listed.text
    assert summary["total"] == listed.json()["total"] == 3
    assert summary["new_today"] == summary["total"]
