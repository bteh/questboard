"""HTTP wiring for the workspace companies store.

The Companies tab talks to /workspace/companies (workspace store the pull
reads), not /profiles/{p}/watchlist (default.yaml the pull ignores). Verifies
the endpoints resolve, persist, list, delete, and map an unsupported link to a
422 with the honest board message.

App modules are imported at fixture time (one consistent generation) because an
earlier test purges app.* from sys.modules — see test_workspace_companies.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def env(monkeypatch):
    from job_finder.models.database import Base
    from app.models.workspace import Workspace, WorkspacePreferences
    from app.api import workspace_companies
    from app.dependencies import get_workspace_context, get_workspace_context_csrf
    from app.models.database import get_db
    from app.services import watchlist_service

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Workspace(id="ws1", name="Local", slug="local-ws1"))
    session.add(
        WorkspacePreferences(
            workspace_id="ws1",
            roles_json=json.dumps(["Data Engineer"]),
            target_companies_json="[]",
            target_companies_meta_json="[]",
        )
    )
    session.commit()

    monkeypatch.setattr(workspace_companies, "enforce_rate_limit", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(workspace_companies.router, prefix="/api/v1")
    fake_context = SimpleNamespace(workspace=SimpleNamespace(id="ws1"))
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_workspace_context] = lambda: fake_context
    app.dependency_overrides[get_workspace_context_csrf] = lambda: fake_context
    try:
        yield SimpleNamespace(client=TestClient(app), watchlist_service=watchlist_service)
    finally:
        session.close()


def test_add_by_name_then_list_and_delete(env, monkeypatch):
    monkeypatch.setattr(
        env.watchlist_service,
        "discover_company",
        lambda name: {"name": name, "slug": "umbra", "ats": "greenhouse", "job_count": 4,
                      "careers_url": "https://boards.greenhouse.io/umbra"},
    )

    added = env.client.post("/api/v1/workspace/companies", json={"name": "Umbra"})
    assert added.status_code == 200
    body = added.json()
    assert body["profile"] == "workspace"
    assert body["companies"] == [
        {"name": "Umbra", "slug": "umbra", "ats": "greenhouse", "job_count": 4,
         "careers_url": "https://boards.greenhouse.io/umbra"}
    ]

    listed = env.client.get("/api/v1/workspace/companies")
    assert [c["name"] for c in listed.json()["companies"]] == ["Umbra"]

    removed = env.client.delete("/api/v1/workspace/companies/Umbra")
    assert removed.json()["companies"] == []


def test_unsupported_link_is_422_with_board_message(env, monkeypatch):
    def _raise(url, name=""):
        raise env.watchlist_service.UnsupportedBoardUrlError(
            "Paste a careers link from Greenhouse, Lever, Ashby, or Workday. "
            "Other job boards are not supported yet."
        )

    monkeypatch.setattr(env.watchlist_service, "resolve_board_url", _raise)

    resp = env.client.post("/api/v1/workspace/companies", json={"url": "https://example.com/careers"})
    assert resp.status_code == 422
    assert "not supported" in resp.json()["detail"].lower()


def test_failed_discovery_returns_honest_message(env, monkeypatch):
    monkeypatch.setattr(
        env.watchlist_service,
        "discover_company",
        lambda name: {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""},
    )

    resp = env.client.post("/api/v1/workspace/companies", json={"name": "Umbra"})
    assert resp.status_code == 200
    body = resp.json()
    assert "careers" in body["message"].lower()
    assert body["companies"] == [
        {"name": "Umbra", "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""}
    ]
