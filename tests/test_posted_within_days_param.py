"""The /applications window params behind the home masthead flap counters.

posted_within_days keeps only rows whose true post date PROVABLY falls in
the window. date_posted is a raw source string: ISO-8601 when the source
stated a real date, free text ("Reposted 9 Days Ago") when it did not. The
filter must count ISO dates inside the window, drop free text, drop rows the
classifier marked missing, and drop date-only strings it cannot prove are
inside a rolling window (undercounting is the honest side of ambiguity).

event_within_days keeps only rows whose taping/session (event_start) falls
inside the next N days: real event dates only, nothing guessed in.
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_posted(jf_db) -> None:
    jf_db.save_application(
        job_title="Posted two hours ago",
        company="Acme",
        job_url="https://example.com/jobs/fresh",
        date_posted=(_now() - timedelta(hours=2)).isoformat(),
        date_confidence="exact",
    )
    jf_db.save_application(
        job_title="Posted two days ago",
        company="Acme",
        job_url="https://example.com/jobs/older",
        date_posted=(_now() - timedelta(days=2)).isoformat(),
        date_confidence="exact",
    )
    # Date-only string from today: provably inside any 24h window that
    # contains today's UTC midnight.
    jf_db.save_application(
        job_title="Date-only today",
        company="Acme",
        job_url="https://example.com/jobs/date-only",
        date_posted=_now().strftime("%Y-%m-%d"),
        date_confidence="exact",
    )
    # Free-text junk a scraper let through; sorts above any ISO date, so the
    # future-bounded upper edge must drop it.
    jf_db.save_application(
        job_title="Free-text repost",
        company="Acme",
        job_url="https://example.com/jobs/repost",
        date_posted="Reposted 9 Days Ago",
        date_confidence="exact",
    )
    jf_db.save_application(
        job_title="Bare day count",
        company="Acme",
        job_url="https://example.com/jobs/barecount",
        date_posted="8 Days Ago",
        date_confidence="exact",
    )
    # A fresh-looking string the classifier does not trust.
    jf_db.save_application(
        job_title="Missing confidence",
        company="Acme",
        job_url="https://example.com/jobs/missing",
        date_posted=_now().isoformat(),
        date_confidence="missing",
    )
    jf_db.save_application(
        job_title="No date at all",
        company="Acme",
        job_url="https://example.com/jobs/nodate",
    )


def _titles(payload: dict) -> set[str]:
    return {item["job_title"] for item in payload["items"]}


def test_no_window_returns_everything(api_client) -> None:
    client, jf_db = api_client
    _seed_posted(jf_db)

    resp = client.get("/api/v1/applications")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 7


def test_posted_within_one_day_counts_only_provable_rows(api_client) -> None:
    client, jf_db = api_client
    _seed_posted(jf_db)

    resp = client.get("/api/v1/applications", params={"posted_within_days": 1})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert _titles(payload) == {"Posted two hours ago", "Date-only today"}
    assert payload["total"] == 2


def test_posted_window_widens_with_days(api_client) -> None:
    client, jf_db = api_client
    _seed_posted(jf_db)

    resp = client.get("/api/v1/applications", params={"posted_within_days": 3})
    assert resp.status_code == 200, resp.text
    assert _titles(resp.json()) == {
        "Posted two hours ago",
        "Posted two days ago",
        "Date-only today",
    }


def test_posted_window_never_guesses_junk_in(api_client) -> None:
    client, jf_db = api_client
    _seed_posted(jf_db)

    resp = client.get("/api/v1/applications", params={"posted_within_days": 30})
    titles = _titles(resp.json())
    assert "Free-text repost" not in titles
    assert "Bare day count" not in titles
    assert "Missing confidence" not in titles
    assert "No date at all" not in titles


def test_posted_within_days_rejects_zero(api_client) -> None:
    client, _ = api_client
    resp = client.get("/api/v1/applications", params={"posted_within_days": 0})
    assert resp.status_code == 422


def _seed_events(jf_db) -> None:
    now = _now().replace(tzinfo=None)
    jf_db.save_application(
        job_title="Taping in three days",
        company="Studio",
        job_url="https://example.com/quests/soon",
        vertical="camera",
        event_start=now + timedelta(days=3),
    )
    jf_db.save_application(
        job_title="Session next month",
        company="Lab",
        job_url="https://example.com/quests/later",
        vertical="study",
        event_start=now + timedelta(days=30),
    )
    jf_db.save_application(
        job_title="Taping already happened",
        company="Studio",
        job_url="https://example.com/quests/past",
        vertical="camera",
        event_start=now - timedelta(days=2),
    )
    jf_db.save_application(
        job_title="Rolling, no event date",
        company="Lab",
        job_url="https://example.com/quests/rolling",
        vertical="study",
        is_rolling=True,
    )


def test_event_within_days_counts_only_real_upcoming_events(api_client) -> None:
    client, jf_db = api_client
    _seed_events(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "camera,study,lens", "event_within_days": 7},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert _titles(payload) == {"Taping in three days"}
    assert payload["total"] == 1


def test_event_window_widens_but_never_counts_the_past_or_dateless(api_client) -> None:
    client, jf_db = api_client
    _seed_events(jf_db)

    resp = client.get(
        "/api/v1/applications",
        params={"vertical": "camera,study,lens", "event_within_days": 60},
    )
    titles = _titles(resp.json())
    assert titles == {"Taping in three days", "Session next month"}
