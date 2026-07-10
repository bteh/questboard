"""The board's place filter: narrow to reachable quests, never hide remote.

Rows pass a location= filter when their location text matches, when they
say remote/online/nationwide in any wording, or when the source stated no
place at all (unknown is not "elsewhere"). The search box also matches the
location field, so a typed city finds the sit whose location names it.
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
    rows = (
        ("LA babysitting", "https://x.example/la", "Culver City, CA", "lookafter"),
        ("Kansas trial", "https://x.example/ks", "Lenexa, KS", "body"),
        ("Online study", "https://x.example/rem", "Remote", "think"),
        ("Nationwide bonus", "https://x.example/us", "nationwide", "house"),
        ("Placeless drop", "https://x.example/none", "", "flip"),
    )
    for title, url, location, vertical in rows:
        jf_db.save_application(
            job_title=title, company="Fixture", job_url=url,
            location=location, vertical=vertical,
        )


VERTS = "lookafter,body,think,house,flip"


def test_place_narrows_but_never_hides_remote_or_placeless(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": VERTS, "location": "Culver City"}
    )
    assert resp.status_code == 200, resp.text
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert titles == {"LA babysitting", "Online study", "Nationwide bonus", "Placeless drop"}


def test_place_matching_is_case_insensitive(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": VERTS, "location": "lenexa"})
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert "Kansas trial" in titles
    assert "LA babysitting" not in titles


def test_search_box_matches_the_location_field(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": VERTS, "search": "Lenexa"})
    titles = {item["job_title"] for item in resp.json()["items"]}
    assert titles == {"Kansas trial"}


def test_no_location_param_returns_everything(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": VERTS})
    assert resp.json()["total"] == 5
