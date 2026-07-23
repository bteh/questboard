"""Layer 3: honest state for entries without a confirmed job board.

A failed discovery used to store an inert entry (ats "unknown",
job_count 0) and return it looking healthy. The add response now says so
in ``message``, the entry keeps its "unknown" ats through GET so the UI
can show it as unfinished, and DELETE still works on it.
"""

from __future__ import annotations

import pytest

from app.services import watchlist_service


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.watchlist import router

    # Keep profile YAML writes inside the test sandbox.
    monkeypatch.setattr(watchlist_service, "_PROJECT_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture()
def discovery_fails(monkeypatch):
    monkeypatch.setattr(
        watchlist_service,
        "discover_company",
        lambda name: {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""},
    )


def test_failed_discovery_says_so_in_the_response_message(client, discovery_fails):
    resp = client.post("/profiles/default/watchlist", json={"name": "Umbra"})

    assert resp.status_code == 200
    body = resp.json()
    assert "Umbra" in body["message"]
    assert "careers" in body["message"].lower()
    # The entry is still stored, honestly marked, so the user can complete it.
    assert body["companies"] == [
        {"name": "Umbra", "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""}
    ]


def test_successful_add_has_no_message(client, monkeypatch):
    monkeypatch.setattr(
        watchlist_service,
        "discover_company",
        lambda name: {
            "name": name,
            "slug": "umbra",
            "ats": "greenhouse",
            "job_count": 3,
            "careers_url": "https://boards.greenhouse.io/umbra",
        },
    )
    resp = client.post("/profiles/default/watchlist", json={"name": "Umbra"})

    assert resp.status_code == 200
    assert resp.json()["message"] == ""


def test_unknown_entries_keep_their_status_through_get(client, discovery_fails):
    client.post("/profiles/default/watchlist", json={"name": "Umbra"})

    resp = client.get("/profiles/default/watchlist")

    assert resp.status_code == 200
    companies = resp.json()["companies"]
    assert companies[0]["ats"] == "unknown"


def test_delete_still_works_for_unknown_entries(client, discovery_fails):
    client.post("/profiles/default/watchlist", json={"name": "Umbra"})

    resp = client.delete("/profiles/default/watchlist/Umbra")

    assert resp.status_code == 200
    assert resp.json()["companies"] == []
