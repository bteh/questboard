"""The /applications first_quest_ok param behind the board's Start here preset.

first_quest_ok=true keeps only rows whose SOURCE stated a beginner-friendly
signal. Career rows never carry the flag and unmarked quest rows default to
False, so both drop rather than get guessed in: undercounting is the honest
side of a missing signal.
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
        job_title="Audience seat, no experience stated",
        company="Studio",
        job_url="https://example.com/quests/seat",
        vertical="camera",
        first_quest_ok=True,
    )
    jf_db.save_application(
        job_title="Paid study, open to anyone",
        company="Lab",
        job_url="https://example.com/quests/study",
        vertical="study",
        first_quest_ok=True,
    )
    jf_db.save_application(
        job_title="Casting call, reel required",
        company="Studio",
        job_url="https://example.com/quests/reel",
        vertical="camera",
    )
    jf_db.save_application(
        job_title="Senior Engineer",
        company="Acme",
        job_url="https://example.com/jobs/senior",
    )


def _titles(payload: dict) -> set[str]:
    return {item["job_title"] for item in payload["items"]}


def test_no_param_returns_everything(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": "career,camera,study,lens"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 4


def test_true_keeps_only_rows_with_the_stated_signal(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "career,camera,study,lens", "first_quest_ok": True},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert _titles(payload) == {
        "Audience seat, no experience stated",
        "Paid study, open to anyone",
    }
    assert payload["total"] == 2


def test_true_never_guesses_career_rows_in(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "career", "first_quest_ok": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


def test_false_keeps_the_unmarked_rows(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "career,camera,study,lens", "first_quest_ok": False},
    )
    assert resp.status_code == 200, resp.text
    assert _titles(resp.json()) == {
        "Casting call, reel required",
        "Senior Engineer",
    }
