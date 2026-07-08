"""The log's personal-quest store: vertical='personal' on the applications table.

Personal quests are rows the user writes in the log composer: title only,
source 'user', no URL. They live in the same table as scraped rows but in
their own lane, and three walls keep that lane honest:

1. save_application and POST /applications accept 'personal' (the direct
   save paths), but /quests/refresh still rejects it: no scraper can ever
   produce a personal row.
2. Career surfaces never see them. The default career scope, the explicit
   vertical=career query (the board's career chip count and the ledger's
   career scope), and the CSV export all exclude personal rows structurally.
3. The ledger's clear-all purge never deletes them: they are the user's own
   writing, not scraped applications.

Also pinned here: the log's API contract. Multiple URL-less rows can
coexist (empty job_url stores as NULL), status accepts a comma list so the
whole log reads in one query, 'shelved' is a real status, quest_json
patches through /applications/{id} (the paid-out figure the user types when
marking a quest done), and updated_at is a sortable column.
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


def _seed_board(jf_db) -> None:
    """One career row and one quest row, the board's world."""
    jf_db.save_application(
        job_title="Staff Data Engineer",
        company="Vercel",
        job_url="https://example.com/jobs/vercel",
        vertical="career",
    )
    jf_db.save_application(
        job_title="Paid sleep study",
        company="Sleep Lab",
        job_url="https://example.com/quests/sleep",
        vertical="study",
    )


def _create_personal(client, title: str) -> dict:
    resp = client.post(
        "/api/v1/applications",
        json={"job_title": title, "source": "user", "vertical": "personal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _titles(payload: dict) -> set[str]:
    return {item["job_title"] for item in payload["items"]}


# ── the store ──────────────────────────────────────────────────────────


def test_save_application_accepts_personal(api_client) -> None:
    _, jf_db = api_client
    record = jf_db.save_application(
        job_title="Learn pottery, wheel class",
        company="",
        vertical="personal",
    )
    assert record is not None
    assert record.vertical == "personal"
    assert record.job_url is None


def test_composer_create_and_many_urlless_rows(api_client) -> None:
    client, _ = api_client
    first = _create_personal(client, "Get my first background acting gig")
    second = _create_personal(client, "Learn pottery, wheel class")
    assert first["vertical"] == "personal"
    assert second["vertical"] == "personal"
    assert first["id"] != second["id"]
    # Empty URLs store as NULL, so the unique constraint never collides.
    assert first["job_url"] == ""
    assert second["job_url"] == ""


def test_create_rejects_unknown_vertical(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        "/api/v1/applications",
        json={"job_title": "Nope", "vertical": "sidequest"},
    )
    assert resp.status_code == 400
    assert "vertical" in resp.json()["detail"]


def test_quests_refresh_still_rejects_personal(api_client) -> None:
    client, _ = api_client
    resp = client.post("/api/v1/quests/refresh", json={"verticals": ["personal"]})
    assert resp.status_code == 400
    assert "personal" not in resp.json()["detail"].split("{")[1]


# ── the walls: career surfaces never see personal rows ────────────────


def test_career_scope_excludes_personal(api_client) -> None:
    client, jf_db = api_client
    _seed_board(jf_db)
    _create_personal(client, "Get my first background acting gig")

    # The ledger's default career scope (no vertical param).
    resp = client.get("/api/v1/applications")
    assert resp.status_code == 200
    assert _titles(resp.json()) == {"Staff Data Engineer"}

    # The board's career chip count: explicit vertical=career, page_size 1.
    resp = client.get(
        "/api/v1/applications", params={"vertical": "career", "page_size": 1}
    )
    assert resp.json()["total"] == 1

    # The board's All chip spans the five board verticals, never personal.
    resp = client.get(
        "/api/v1/applications", params={"vertical": "career,camera,study,lens"}
    )
    assert _titles(resp.json()) == {"Staff Data Engineer", "Paid sleep study"}

    # The log opts in explicitly and sees the personal lane.
    resp = client.get("/api/v1/applications", params={"vertical": "personal"})
    assert _titles(resp.json()) == {"Get my first background acting gig"}


def test_csv_export_excludes_personal(api_client) -> None:
    client, jf_db = api_client
    _seed_board(jf_db)
    _create_personal(client, "Get my first background acting gig")

    resp = client.get("/api/v1/applications/export/csv")
    assert resp.status_code == 200
    assert "Staff Data Engineer" in resp.text
    assert "background acting gig" not in resp.text


def test_purge_all_keeps_personal_rows(api_client) -> None:
    client, jf_db = api_client
    _seed_board(jf_db)
    _create_personal(client, "Get my first background acting gig")

    resp = client.post("/api/v1/applications/purge-all", params={"confirm": "true"})
    assert resp.status_code == 200
    assert resp.json()["purged"] == 2

    resp = client.get("/api/v1/applications", params={"vertical": "personal"})
    assert _titles(resp.json()) == {"Get my first background acting gig"}


# ── the log's API contract ─────────────────────────────────────────────


def test_status_accepts_comma_list(api_client) -> None:
    client, jf_db = api_client
    _seed_board(jf_db)
    personal = _create_personal(client, "Get my first background acting gig")

    ids = {}
    resp = client.get("/api/v1/applications", params={"vertical": "study"})
    ids["study"] = resp.json()["items"][0]["id"]
    client.patch(f"/api/v1/applications/{ids['study']}/status", json={"status": "clipped"})
    client.patch(f"/api/v1/applications/{personal['id']}/status", json={"status": "shelved"})

    resp = client.get(
        "/api/v1/applications",
        params={
            "vertical": "career,camera,study,lens,party,personal",
            "status": "clipped,shelved",
        },
    )
    assert resp.status_code == 200
    assert _titles(resp.json()) == {
        "Paid sleep study",
        "Get my first background acting gig",
    }

    # A single status keeps working exactly as before.
    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "personal", "status": "shelved"},
    )
    assert _titles(resp.json()) == {"Get my first background acting gig"}


def test_shelved_is_a_real_status(api_client) -> None:
    client, _ = api_client
    personal = _create_personal(client, "Learn pottery, wheel class")
    resp = client.patch(
        f"/api/v1/applications/{personal['id']}/status", json={"status": "shelved"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "shelved"


def test_quest_json_patches_the_paid_figure(api_client) -> None:
    client, _ = api_client
    personal = _create_personal(client, "Did a paid snack focus group")

    resp = client.patch(
        f"/api/v1/applications/{personal['id']}",
        json={"status": "paid_out", "quest_json": '{"paid_out": 125}'},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "paid_out"
    assert body["quest"] == {"paid_out": 125}

    # Not an object: rejected before it can corrupt the row.
    resp = client.patch(
        f"/api/v1/applications/{personal['id']}",
        json={"quest_json": "[125]"},
    )
    assert resp.status_code == 422


def test_updated_at_is_sortable(api_client) -> None:
    client, _ = api_client
    older = _create_personal(client, "Older quest")
    _create_personal(client, "Newer quest")

    # Touching the older row bumps it to the top of an updated_at sort.
    client.patch(f"/api/v1/applications/{older['id']}/status", json={"status": "shelved"})
    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "personal", "sort_by": "updated_at", "sort_dir": "desc"},
    )
    titles = [item["job_title"] for item in resp.json()["items"]]
    assert titles == ["Older quest", "Newer quest"]
