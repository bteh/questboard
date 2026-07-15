"""The board's facet filter: a kind's own sub-shelves, never a guess.

facet= resolves against the requested verticals through the kinds registry
(packages/kinds/kinds.json) and keeps rows whose title or description
carries one of the facet's stated terms. A facet the requested kinds do
not carry is a 400, not an empty board.
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
        ("Dog boarding, weekend", "https://x.example/dog", "Sitter needed for a friendly dog", "lookafter"),
        ("Overnight sit", "https://x.example/cat", "Two cats, food and litter provided", "lookafter"),
        ("Weekend nanny", "https://x.example/kid", "Watch two kids Saturday mornings", "lookafter"),
        ("House sitting, two weeks", "https://x.example/house", "Water the plants, collect the mail", "lookafter"),
        ("Paid focus group on snacks", "https://x.example/fg", "90-minute session, in person", "think"),
        ("Mock juror, civil case", "https://x.example/jury", "Full-day mock trial exercise", "think"),
    )
    for title, url, description, vertical in rows:
        jf_db.save_application(
            job_title=title, company="Fixture", job_url=url,
            description=description, vertical=vertical,
        )


def test_facet_narrows_by_title_and_description(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": "lookafter", "facet": "pets"}
    )
    assert resp.status_code == 200, resp.text
    titles = {item["job_title"] for item in resp.json()["items"]}
    # the dog row matches on its title, the cat row only on its description
    assert titles == {"Dog boarding, weekend", "Overnight sit"}


def test_each_facet_is_its_own_shelf(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    kids = client.get(
        "/api/v1/applications", params={"vertical": "lookafter", "facet": "kids"}
    )
    assert {i["job_title"] for i in kids.json()["items"]} == {"Weekend nanny"}

    houses = client.get(
        "/api/v1/applications", params={"vertical": "lookafter", "facet": "houses"}
    )
    assert {i["job_title"] for i in houses.json()["items"]} == {"House sitting, two weeks"}

    juries = client.get(
        "/api/v1/applications", params={"vertical": "think", "facet": "juries"}
    )
    assert {i["job_title"] for i in juries.json()["items"]} == {"Mock juror, civil case"}


def test_no_facet_returns_the_whole_lane(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"vertical": "lookafter"})
    assert resp.json()["total"] == 4


def test_facet_total_is_the_filtered_count(api_client) -> None:
    # the chips' counts are this total, so it must match the filtered rows
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "lookafter", "facet": "pets", "page_size": 1},
    )
    assert resp.json()["total"] == 2


def test_facet_from_another_kind_is_a_400(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": "think", "facet": "pets"}
    )
    assert resp.status_code == 400
    assert "facet" in resp.json()["detail"]


def test_unknown_facet_is_a_400(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get(
        "/api/v1/applications", params={"vertical": "lookafter", "facet": "nope"}
    )
    assert resp.status_code == 400
