"""HTTP wiring for Places I'd work at (/watched-pages).

Add validates the link and reads the page once (core check_page is stubbed),
list returns pages plus starter suggestions not yet added, remove deletes.
App modules are imported at fixture time, as in test_workspace_companies_api.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ELOREA = "https://elorea.com/pages/career-opportunities"


@pytest.fixture()
def env(monkeypatch):
    from job_finder.tools.scrapers import watched_pages as source
    from app.api import watched_pages
    from app.dependencies import get_workspace_context, get_workspace_context_csrf
    from app.models.database import get_db
    from app.models.workspace import Workspace
    from app.services import local_agent_service, watched_pages_service

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # an earlier test may purge app.* and job_finder.models.*; create the
    # tables from the generations these modules actually bound to
    Workspace.metadata.create_all(engine)
    watched_pages_service.store.WatchedPageRecord.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Workspace(id="ws1", name="Local", slug="local-ws1"))
    session.commit()

    monkeypatch.setattr(watched_pages, "enforce_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(local_agent_service, "saved_place", lambda db, ws=None: "Koreatown, LA")
    checked: list[tuple[str, str | None]] = []

    def fake_check(url, place=None, name=""):
        checked.append((url, place))
        if "blocked" in url:
            return {"name": "", "found": 0, "rows": [], "error":
                    "That site's robots.txt asks tools not to read this page.", "via": ""}
        return {"name": "ELOREA", "found": 6, "error": "", "via": "listing",
                "rows": [{"title": "Barista (LA)"}, {"title": "Scent Advisor (Sales Associate) LA"}]}

    monkeypatch.setattr(source, "check_page", fake_check)

    app = FastAPI()
    app.include_router(watched_pages.router, prefix="/api/v1")
    ctx = SimpleNamespace(workspace=SimpleNamespace(id="ws1"))
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_workspace_context] = lambda: ctx
    app.dependency_overrides[get_workspace_context_csrf] = lambda: ctx
    try:
        yield SimpleNamespace(client=TestClient(app), checked=checked)
    finally:
        session.close()


def test_add_list_remove(env):
    first = env.client.get("/api/v1/watched-pages").json()
    assert first["pages"] == []
    assert ELOREA in [s["url"] for s in first["suggestions"]]

    added = env.client.post("/api/v1/watched-pages", json={"url": ELOREA})
    assert added.status_code == 200
    body = added.json()
    assert env.checked == [(ELOREA, "Koreatown, LA")]
    assert [(p["name"], p["url"], p["last_found"]) for p in body["pages"]] == [
        ("ELOREA", ELOREA, 2)
    ]
    assert body["message"].startswith("2 part-time openings near you")
    assert ELOREA not in [s["url"] for s in body["suggestions"]]

    listed = env.client.get("/api/v1/watched-pages").json()
    assert [p["url"] for p in listed["pages"]] == [ELOREA]

    page_id = listed["pages"][0]["id"]
    removed = env.client.delete(f"/api/v1/watched-pages/{page_id}").json()
    assert removed["pages"] == []
    assert ELOREA in [s["url"] for s in removed["suggestions"]]


def test_adding_twice_keeps_one_row(env):
    env.client.post("/api/v1/watched-pages", json={"url": ELOREA})
    again = env.client.post("/api/v1/watched-pages", json={"url": ELOREA}).json()
    assert len(again["pages"]) == 1


@pytest.mark.parametrize("bad", ["", "elorea.com/pages/careers", "ftp://elorea.com/x", "https://localhost/x"])
def test_bad_link_is_422_and_never_fetched(env, bad):
    resp = env.client.post("/api/v1/watched-pages", json={"url": bad})
    assert resp.status_code == 422
    assert "http" in resp.json()["detail"]
    assert env.checked == []


def test_unreadable_page_is_422_with_plain_reason_and_not_saved(env):
    resp = env.client.post("/api/v1/watched-pages", json={"url": "https://blocked.example.com/jobs"})
    assert resp.status_code == 422
    assert "robots.txt" in resp.json()["detail"]
    assert env.client.get("/api/v1/watched-pages").json()["pages"] == []


def test_hosted_mode_hides_the_route(env, monkeypatch):
    from app.api import watched_pages

    monkeypatch.setattr(
        watched_pages, "reject_legacy_route_in_hosted_mode",
        lambda detail="": (_ for _ in ()).throw(
            __import__("fastapi").HTTPException(404, detail)
        ),
    )
    assert env.client.get("/api/v1/watched-pages").status_code == 404
