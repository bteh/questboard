"""Quest ingestion path: run_quest_search, /quests/refresh, board filters.

run_quest_search must select only the requested quest verticals (career
scrapers never run), pass query/geo hints only to scrapers that declare
them, persist quest kwargs faithfully through save_application, skip
already-past events at ingest, and count dedup via the job_url upsert. The
refresh endpoint validates verticals; the applications API grows
upcoming_only and event_start sort; auto-apply routes refuse quest rows
loudly.
"""

from __future__ import annotations

import json
import os
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

from job_finder.tools.scrapers import get_registry, register_scraper  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    from job_finder.models import database

    database.init_db(os.path.join(str(tmp_path), "job_tracker.db"))
    yield database
    if database._SessionLocal is not None:
        database._SessionLocal.remove()


# What each fake scraper actually received, keyed by scraper name.
_RECEIVED: dict[str, dict] = {}


@pytest.fixture()
def fake_party_scrapers():
    """Two quest scrapers on the 'party' vertical (no real scrapers there, so
    the REAL run_scrapers path runs without touching the network). One
    declares query/geo params, one only tolerates **kwargs."""
    _RECEIVED.clear()
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    @register_scraper(
        name="fake_party_geo",
        display_name="Fake Party Geo",
        url="https://party.example",
        category="party",
        vertical="party",
        enabled_by_default=False,
    )
    def _geo(
        roles=None, max_results=50,
        query=None, lat=None, lon=None, radius_miles=50,
        **kwargs,
    ):
        _RECEIVED["fake_party_geo"] = {
            "query": query, "lat": lat, "lon": lon, "radius_miles": radius_miles,
        }
        return [
            {
                "title": "Warehouse crew: door help",
                "company": "Fake Party Geo",
                "location": "Brooklyn, NY",
                "url": "https://party.example/quest/1",
                "source": "fake_party_geo",
                "vertical": "party",
                "description": "Help run the door for one night.",
                "first_quest_ok": True,
                "event_start": future,
                "event_end": future,
                "quest": {"headcount": 4, "age_min": 21},
            },
            {  # stale: the event already happened
                "title": "Last week's show",
                "company": "Fake Party Geo",
                "url": "https://party.example/quest/2",
                "source": "fake_party_geo",
                "vertical": "party",
                "event_start": past,
            },
            {  # rolling signup, no date: always passes the stale gate
                "title": "Standing crew list",
                "company": "Fake Party Geo",
                "url": "https://party.example/quest/3",
                "source": "fake_party_geo",
                "vertical": "party",
                "is_rolling": True,
            },
            {  # same URL as the first row: the job_url upsert dedups it
                "title": "Warehouse crew: door help",
                "company": "Fake Party Geo",
                "url": "https://party.example/quest/1",
                "source": "fake_party_geo",
                "vertical": "party",
                "event_start": future,
            },
        ]

    @register_scraper(
        name="fake_party_plain",
        display_name="Fake Party Plain",
        url="https://party2.example",
        category="party",
        vertical="party",
        enabled_by_default=False,
    )
    def _plain(roles=None, max_results=50, **kwargs):
        _RECEIVED["fake_party_plain"] = dict(kwargs)
        return [
            {
                "title": "Door list helper",
                "company": "Fake Party Plain",
                "url": "https://party2.example/quest/1",
                "source": "fake_party_plain",
                "vertical": "party",
                "first_quest_ok": True,
                "quest": {"pay_text": "$50"},
            }
        ]

    yield ("fake_party_geo", "fake_party_plain")
    get_registry().pop("fake_party_geo", None)
    get_registry().pop("fake_party_plain", None)


# ---------------------------------------------------------------------------
# run_quest_search


def test_selects_only_requested_vertical_scrapers(db, monkeypatch):
    from job_finder import quests

    captured: dict = {}

    def fake_run_scrapers(names=None, **kwargs):
        captured["names"] = list(names or [])
        return []

    monkeypatch.setattr(quests, "run_scrapers", fake_run_scrapers)
    summary = quests.run_quest_search(["camera"])

    registry = get_registry()
    assert captured["names"], "camera scrapers should be selected"
    assert all(registry[n].vertical == "camera" for n in captured["names"])
    assert summary["verticals"] == ["camera"]
    assert set(summary["sources"]) == set(captured["names"])


def test_career_is_never_selected(db, monkeypatch):
    from job_finder import quests

    calls: list = []
    monkeypatch.setattr(quests, "run_scrapers", lambda **k: calls.append(k) or [])
    summary = quests.run_quest_search(["career"])
    assert calls == []
    assert summary["found"] == 0
    assert summary["saved"] == 0
    assert summary["sources"] == {}


def test_quest_module_never_touches_career_machinery():
    import inspect

    from job_finder import quests

    src = inspect.getsource(quests)
    for banned in ("JobFinderPipeline", "purge_", "backfill_", "score_job", "parse_resume"):
        assert banned not in src, f"quests.py must never reference {banned}"


def test_run_quest_search_persists_skips_stale_and_dedups(db, fake_party_scrapers):
    from job_finder.quests import run_quest_search

    summary = run_quest_search(
        ["party"], query="door", lat=40.7, lon=-74.0, radius_miles=25,
    )

    # Geo/query hints reach only the scraper that declares them.
    assert _RECEIVED["fake_party_geo"] == {
        "query": "door", "lat": 40.7, "lon": -74.0, "radius_miles": 25,
    }
    assert "query" not in _RECEIVED["fake_party_plain"]
    assert "lat" not in _RECEIVED["fake_party_plain"]

    assert summary["found"] == 5
    assert summary["saved"] == 3
    assert summary["deduped"] == 1
    assert summary["skipped_stale"] == 1
    assert summary["sources"]["fake_party_geo"] == {
        "found": 4, "saved": 2, "deduped": 1, "skipped_stale": 1,
    }
    assert summary["sources"]["fake_party_plain"] == {
        "found": 1, "saved": 1, "deduped": 0, "skipped_stale": 0,
    }

    rows = {r.job_url: r for r in db.get_all_applications(verticals=["party"])}
    assert len(rows) == 3

    crew = rows["https://party.example/quest/1"]
    assert crew.vertical == "party"
    assert crew.first_quest_ok is True
    assert crew.is_rolling is False
    assert crew.event_start is not None
    assert crew.event_end is not None
    assert json.loads(crew.quest_json) == {"headcount": 4, "age_min": 21}

    rolling = rows["https://party.example/quest/3"]
    assert rolling.is_rolling is True
    assert rolling.event_start is None

    # No leakage into the career lane.
    assert db.get_all_applications() == []


def test_second_run_dedups_everything(db, fake_party_scrapers):
    from job_finder.quests import run_quest_search

    run_quest_search(["party"])
    second = run_quest_search(["party"])
    assert second["saved"] == 0
    assert second["deduped"] == 4  # 3 known rows + the in-run duplicate URL
    assert second["skipped_stale"] == 1
    assert len(db.get_all_applications(verticals=["party"])) == 3


# ---------------------------------------------------------------------------
# API level


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


def test_refresh_endpoint_validates_verticals(api_client):
    client, _jf_db = api_client
    for bad in (["bogus"], ["career"], [], ["camera", "bogus"]):
        resp = client.post("/api/v1/quests/refresh", json={"verticals": bad})
        assert resp.status_code == 400, f"{bad}: {resp.text}"

    # The vocabulary derives from the kinds registry, never a hand list: a
    # lane with no scrapers yet (party) is a valid no-op refresh, so a new
    # kind is refreshable the moment its first scraper ships.
    resp = client.post("/api/v1/quests/refresh", json={"verticals": ["party"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["sources"] == {}


def test_refresh_endpoint_runs_and_returns_summary(api_client, monkeypatch):
    client, _jf_db = api_client
    import job_finder.quests as quests

    calls: dict = {}

    def fake_run(
        verticals, *, query=None, lat=None, lon=None, radius_miles=None,
        workspace_id=None, progress=None,
    ):
        calls["args"] = (list(verticals), query, lat, lon, radius_miles)
        calls["workspace_id"] = workspace_id
        return {
            "verticals": sorted(set(verticals)),
            "found": 2, "saved": 1, "deduped": 1, "skipped_stale": 0,
            "sources": {"1iota": {"found": 2, "saved": 1, "deduped": 1, "skipped_stale": 0}},
        }

    monkeypatch.setattr(quests, "run_quest_search", fake_run)
    resp = client.post(
        "/api/v1/quests/refresh",
        json={
            "verticals": ["camera", "study"],
            "query": "tv taping",
            "lat": 40.7, "lon": -74.0, "radius_miles": 30,
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["saved"] == 1
    assert payload["deduped"] == 1
    assert payload["sources"]["1iota"]["found"] == 2
    assert calls["args"] == (["camera", "study"], "tv taping", 40.7, -74.0, 30)


def test_local_refresh_writes_into_the_shared_pool(api_client, monkeypatch):
    """Local mode owns ONE pool: a cookied session's refresh must save rows
    with workspace_id None, where the (unscoped) local board reads them.
    Threading the session workspace here split the pool in two: rows became
    invisible to the CLI, to other sessions, and to this session once its
    cookie rotated. Hosted refreshes still scope per visitor workspace
    (see workspace_scope_id)."""
    client, _jf_db = api_client
    import job_finder.quests as quests

    boot = client.post("/api/v1/session/bootstrap")
    assert boot.status_code == 200, boot.text

    seen: dict = {}

    def fake_run(verticals, *, workspace_id=None, **_kwargs):
        seen["workspace_id"] = workspace_id
        return {
            "verticals": sorted(set(verticals)),
            "found": 0, "saved": 0, "deduped": 0, "skipped_stale": 0,
            "sources": {},
        }

    monkeypatch.setattr(quests, "run_quest_search", fake_run)
    resp = client.post("/api/v1/quests/refresh", json={"verticals": ["camera"]})
    assert resp.status_code == 200, resp.text
    assert seen["workspace_id"] is None, "local refresh must write the shared pool"


def test_run_quest_search_stamps_workspace_on_saved_rows(db, fake_party_scrapers):
    from job_finder.quests import run_quest_search

    run_quest_search(["party"], workspace_id="ws-quest-test")
    rows = db.get_all_applications(verticals=["party"], workspace_id="ws-quest-test")
    assert len(rows) == 3
    assert all(r.workspace_id == "ws-quest-test" for r in rows)


def test_prepare_and_apply_refuse_quest_rows(api_client):
    client, jf_db = api_client
    quest = jf_db.save_application(
        job_title="Audience seat: The Late Show", company="1iota",
        job_url="https://1iota.com/event/1", source="1iota", vertical="camera",
    )

    resp = client.post(f"/api/v1/applications/{quest.id}/prepare")
    assert resp.status_code == 400, resp.text
    assert "career" in resp.json()["detail"].lower()

    resp = client.post(f"/api/v1/applications/{quest.id}/apply", json={})
    assert resp.status_code == 400, resp.text
    assert "career" in resp.json()["detail"].lower()


def _seed_camera_events(jf_db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    jf_db.save_application(
        job_title="Yesterday taping", company="1iota",
        job_url="https://1iota.com/event/past", source="1iota",
        vertical="camera", event_start=now - timedelta(days=2),
    )
    jf_db.save_application(
        job_title="Tomorrow taping", company="1iota",
        job_url="https://1iota.com/event/soon", source="1iota",
        vertical="camera", event_start=now + timedelta(days=1),
    )
    jf_db.save_application(
        job_title="Next week taping", company="1iota",
        job_url="https://1iota.com/event/later", source="1iota",
        vertical="camera", event_start=now + timedelta(days=7),
    )
    jf_db.save_application(
        job_title="Standing list", company="SRO",
        job_url="https://sro.example/list", source="standingroomonly",
        vertical="camera", is_rolling=True,
    )


def test_upcoming_only_filter(api_client):
    client, jf_db = api_client
    _seed_camera_events(jf_db)

    default = client.get(
        "/api/v1/applications", params={"vertical": "camera"}
    ).json()
    assert default["total"] == 4

    upcoming = client.get(
        "/api/v1/applications",
        params={"vertical": "camera", "upcoming_only": True},
    ).json()
    titles = {item["job_title"] for item in upcoming["items"]}
    assert upcoming["total"] == 3
    assert "Yesterday taping" not in titles
    assert "Standing list" in titles  # NULL event_start passes


def test_event_start_sort(api_client):
    client, jf_db = api_client
    _seed_camera_events(jf_db)
    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "camera", "sort_by": "event_start", "sort_dir": "asc"},
    ).json()
    titles = [item["job_title"] for item in resp["items"]]
    assert titles == [
        "Yesterday taping", "Tomorrow taping", "Next week taping", "Standing list",
    ]


def test_response_exposes_parsed_quest_object(api_client):
    client, jf_db = api_client
    jf_db.save_application(
        job_title="Audience seat", company="1iota",
        job_url="https://1iota.com/event/9", source="1iota", vertical="camera",
        first_quest_ok=True, event_start=datetime(2027, 1, 5, 16, 0),
        quest_json='{"show": "The Late Show", "age_min": 16}',
    )
    item = client.get(
        "/api/v1/applications", params={"vertical": "camera"}
    ).json()["items"][0]
    assert item["vertical"] == "camera"
    assert item["first_quest_ok"] is True
    assert item["is_rolling"] is False
    assert item["quest"] == {"show": "The Late Show", "age_min": 16}
    assert item["quest_json"]
    assert item["event_start"].startswith("2027-01-05")
    assert item["event_end"] is None
