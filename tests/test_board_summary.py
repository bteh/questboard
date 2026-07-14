"""/board/summary: per-kind supply for the board rail.

Stored rows keep their historical vertical values; the endpoint maps them to
kinds via packages/kinds/kinds.json at read time. Dead URLs and the log's
personal lane never count. Kinds with zero supply still appear so the client
can render supply honesty instead of pretending the kind does not exist.
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
        job_title="Senior Engineer",
        company="Acme",
        job_url="https://example.com/jobs/senior",
    )  # vertical defaults to career -> work (its own Jobs lane)
    jf_db.save_application(
        job_title="Second shooter",
        company="r/forhire",
        job_url="https://example.com/quests/shooter",
        vertical="lens",
    )  # lens -> skill (freelance/gigs stay a side-quest)
    jf_db.save_application(
        job_title="Snack focus group",
        company="Fieldwork",
        job_url="https://example.com/quests/snack",
        vertical="study",
    )  # study -> think
    jf_db.save_application(
        job_title="Background actor",
        company="Project Casting",
        job_url="https://example.com/quests/extra",
        vertical="camera",
    )  # camera -> perform


def _kind(payload: dict, kind_id: str) -> dict:
    return next(k for k in payload["kinds"] if k["id"] == kind_id)


def test_counts_map_legacy_verticals_onto_kinds(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/board/summary")
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["total"] == 4
    assert _kind(payload, "work")["count"] == 1  # career sits in its own Jobs lane
    assert _kind(payload, "skill")["count"] == 1  # lens (freelance/gigs) only
    assert _kind(payload, "think")["count"] == 1
    assert _kind(payload, "perform")["count"] == 1


def test_zero_supply_kinds_still_appear_for_supply_honesty(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = client.get("/api/v1/board/summary").json()
    ids = [k["id"] for k in payload["kinds"]]
    for expected in ("odd", "deliver", "lookafter", "flip", "house", "body", "party"):
        assert expected in ids
    assert _kind(payload, "deliver")["count"] == 0
    # ordered by the registry's display order
    orders = [k["order"] for k in payload["kinds"]]
    assert orders == sorted(orders)


def test_dead_personal_and_past_event_rows_never_count(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    session = jf_db._SessionLocal()
    try:
        from datetime import datetime, timedelta, timezone

        from job_finder.models.database import ApplicationRecord

        dead = ApplicationRecord(
            job_title="Gone listing",
            company="Ghost Co",
            job_url="https://example.com/jobs/gone",
            vertical="career",
            url_status="dead",
        )
        personal = ApplicationRecord(
            job_title="My own note",
            company="me",
            job_url="https://example.com/personal/note",
            vertical="personal",
        )
        past_taping = ApplicationRecord(
            job_title="Yesterday's audience seat",
            company="Studio",
            job_url="https://example.com/quests/past",
            vertical="camera",
            event_start=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2),
        )
        past_sit = ApplicationRecord(
            job_title="Last week's sit",
            company="Sittercity",
            job_url="https://example.com/quests/past-sit",
            vertical="lookafter",
            event_start=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7),
        )
        session.add_all([dead, personal, past_taping, past_sit])
        session.commit()
    finally:
        session.close()

    payload = client.get("/api/v1/board/summary").json()
    assert payload["total"] == 4


def test_stale_casting_by_publish_date_never_counts(api_client) -> None:
    """Casting calls carry their audition date only in the text, so event_start
    is NULL and the upcoming filter can't expire them. Once the source publish
    date is past the shelf life the call has passed and drops off the board.
    ISO dates expire; free text, absent dates, and real future events stay."""
    client, jf_db = api_client
    _seed(jf_db)  # includes one camera row with no date -> perform starts at 1

    session = jf_db._SessionLocal()
    try:
        from datetime import datetime, timedelta, timezone

        from job_finder.models.database import ApplicationRecord

        now = datetime.now(timezone.utc)
        iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S")  # noqa: E731

        stale = ApplicationRecord(
            job_title="Auditions JUNE 15 (already past)",
            company="AuditionsFree",
            job_url="https://example.com/quests/stale-cast",
            vertical="camera",
            date_posted=iso(now - timedelta(days=40)),  # ISO, past the shelf life
        )
        fresh = ApplicationRecord(
            job_title="Rush call this week",
            company="AuditionsFree",
            job_url="https://example.com/quests/fresh-cast",
            vertical="camera",
            date_posted=iso(now - timedelta(days=5)),
        )
        freetext = ApplicationRecord(
            job_title="Reposted casting call",
            company="AuditionsFree",
            job_url="https://example.com/quests/freetext-cast",
            vertical="camera",
            date_posted="Reposted 40 Days Ago",  # not ISO -> conservatively kept
        )
        future_event = ApplicationRecord(
            job_title="Old post, future taping",
            company="1iota",
            job_url="https://example.com/quests/future-cast",
            vertical="camera",
            date_posted=iso(now - timedelta(days=40)),
            event_start=(now + timedelta(days=10)).replace(tzinfo=None),  # real date wins
        )
        session.add_all([stale, fresh, freetext, future_event])
        session.commit()
    finally:
        session.close()

    payload = client.get("/api/v1/board/summary").json()
    # seed camera (1) + fresh + freetext + future_event = 4; only `stale` drops
    assert _kind(payload, "perform")["count"] == 4


def test_past_event_day_is_stale_for_every_vertical(api_client) -> None:
    """The read-time stale filter: an event day (UTC) that already passed
    expires the row no matter the vertical. Today and future events stay,
    rows with no event date pass untouched, and the camera publish-date
    shelf life keeps working."""
    _, jf_db = api_client

    session = jf_db._SessionLocal()
    try:
        from datetime import datetime, timedelta, timezone

        from app.services.application_service import time_sensitive_stale
        from job_finder.models.database import ApplicationRecord

        now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)

        rows = {
            "past_camera": ApplicationRecord(
                job_title="Taping two days ago",
                company="Studio",
                job_url="https://example.com/quests/stale-past-camera",
                vertical="camera",
                event_start=datetime(2026, 7, 12, 21, 15),
            ),
            "past_lookafter": ApplicationRecord(
                job_title="Sit last night",
                company="Sittercity",
                job_url="https://example.com/quests/stale-past-sit",
                vertical="lookafter",
                event_start=datetime(2026, 7, 13, 23, 0),
            ),
            "today_body": ApplicationRecord(
                job_title="Session earlier today still shows",
                company="Clinic",
                job_url="https://example.com/quests/stale-today-body",
                vertical="body",
                event_start=datetime(2026, 7, 14, 0, 30),
            ),
            "future_camera": ApplicationRecord(
                job_title="Taping next week",
                company="Studio",
                job_url="https://example.com/quests/stale-future-camera",
                vertical="camera",
                event_start=datetime(2026, 7, 21, 20, 0),
            ),
            "no_date_study": ApplicationRecord(
                job_title="Rolling signup, no date",
                company="Fieldwork",
                job_url="https://example.com/quests/stale-no-date",
                vertical="study",
            ),
            "shelf_camera": ApplicationRecord(
                job_title="Old casting call, date only in the text",
                company="AuditionsFree",
                job_url="https://example.com/quests/stale-shelf-camera",
                vertical="camera",
                date_posted=(now - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        }
        session.add_all(rows.values())
        session.commit()
        ids = {name: row.id for name, row in rows.items()}

        kept = {
            row_id
            for (row_id,) in session.query(ApplicationRecord.id)
            .filter(ApplicationRecord.id.in_(list(ids.values())))
            .filter(~time_sensitive_stale(ApplicationRecord, now=now))
        }
    finally:
        session.close()

    assert ids["past_camera"] not in kept
    assert ids["past_lookafter"] not in kept
    assert ids["shelf_camera"] not in kept
    assert ids["today_body"] in kept
    assert ids["future_camera"] in kept
    assert ids["no_date_study"] in kept


def test_free_text_event_start_is_conservatively_kept(api_client) -> None:
    """SQLite happily stores text in a datetime column. Text that is not an
    ISO date can't prove the event passed, so the row stays on the board,
    same stance as free-text date_posted."""
    _, jf_db = api_client

    session = jf_db._SessionLocal()
    try:
        from datetime import datetime, timezone

        from sqlalchemy import text as sql_text

        from app.services.application_service import time_sensitive_stale
        from job_finder.models.database import ApplicationRecord

        row = ApplicationRecord(
            job_title="Casting call, date buried in the text",
            company="AuditionsFree",
            job_url="https://example.com/quests/free-text-event",
            vertical="camera",
            date_posted=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        )
        session.add(row)
        session.commit()
        row_id = row.id
        # the ORM refuses a str for a DateTime column, so plant it raw,
        # the same way junk lands in a live SQLite file
        session.execute(
            sql_text("UPDATE applications SET event_start = 'auditions June 15' WHERE id = :id"),
            {"id": row_id},
        )
        session.commit()

        now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
        kept = (
            session.query(ApplicationRecord.id)
            .filter(ApplicationRecord.id == row_id)
            .filter(~time_sensitive_stale(ApplicationRecord, now=now))
            .count()
        )
    finally:
        session.close()

    assert kept == 1


def test_expired_tombstones_stay_off_the_board(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    session = jf_db._SessionLocal()
    try:
        from job_finder.models.database import ApplicationRecord

        row = session.query(ApplicationRecord).filter_by(vertical="study").first()
        row.url_status = "expired"
        session.commit()
    finally:
        session.close()

    payload = client.get("/api/v1/board/summary").json()
    assert payload["total"] == 3
    assert _kind(payload, "think")["count"] == 0


def test_fresh_rows_count_as_new_today(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    payload = client.get("/api/v1/board/summary").json()
    # everything just seeded counts as new within 24h
    assert payload["new_today"] == payload["total"] == 4
    assert _kind(payload, "work")["new_today"] == 1  # the career row
    assert _kind(payload, "skill")["new_today"] == 1  # the lens row
