"""Recruiting-status re-verification for ClinicalTrials.gov rows.

ctgov study pages answer HTTP 200 forever, so dead-link checks never
catch a trial that stopped recruiting. These tests pin the contract of
job_finder.trial_status.reverify_trials: the registry's overallStatus
is the only evidence, RECRUITING keeps a row (and refreshes
last_seen_at), anything else tombstones it the way expiry.py does
(url_status="expired"), and a failed check never expires anything.
All API responses are mocked; no test talks to clinicaltrials.gov.
"""

from __future__ import annotations

import asyncio
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
def db(tmp_path):
    import importlib

    for module_name in list(sys.modules):
        if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
            sys.modules.pop(module_name, None)
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(tmp_path / "trials.db"))
    yield jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_trial(db, nct_id: str, *, seen_days_ago: float | None = 40) -> int:
    record = db.save_application(
        job_title=f"Study {nct_id}",
        company="Fixture University",
        job_url=f"https://clinicaltrials.gov/study/{nct_id}",
        source="clinicaltrials",
        vertical="body",
    )
    if seen_days_ago is not None:
        session = db.get_session()
        try:
            row = session.get(db.ApplicationRecord, record.id)
            row.last_seen_at = _utcnow() - timedelta(days=seen_days_ago)
            session.commit()
        finally:
            session.close()
    return record.id


def _row(db, row_id: int):
    session = db.get_session()
    try:
        return session.get(db.ApplicationRecord, row_id)
    finally:
        session.close()


def _payload(*pairs: tuple[str, str]) -> dict:
    return {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": nct},
                    "statusModule": {"overallStatus": status},
                }
            }
            for nct, status in pairs
        ]
    }


def test_recruiting_row_is_kept_and_vouched_for(db, monkeypatch):
    import job_finder.trial_status as ts

    row_id = _seed_trial(db, "NCT01000001", seen_days_ago=40)
    monkeypatch.setattr(
        ts, "_get_json", lambda url, params=None, **kw: _payload(("NCT01000001", "RECRUITING"))
    )

    result = ts.reverify_trials()
    assert result == {"checked": 1, "expired": 0, "kept": 1, "errors": 0}
    row = _row(db, row_id)
    assert row.url_status == "alive"
    assert row.last_checked_at is not None
    # the registry vouched for the study, so the staleness TTL restarts
    assert row.last_seen_at > _utcnow() - timedelta(days=1)


def test_closed_trial_is_expired(db, monkeypatch):
    import job_finder.trial_status as ts

    row_id = _seed_trial(db, "NCT01000002")
    monkeypatch.setattr(
        ts, "_get_json", lambda url, params=None, **kw: _payload(("NCT01000002", "COMPLETED"))
    )

    result = ts.reverify_trials()
    assert result == {"checked": 1, "expired": 1, "kept": 0, "errors": 0}
    assert _row(db, row_id).url_status == "expired"


def test_enrolling_by_invitation_counts_as_closed(db, monkeypatch):
    # active, but only pre-selected participants may join: not a board offer
    import job_finder.trial_status as ts

    row_id = _seed_trial(db, "NCT01000003")
    monkeypatch.setattr(
        ts,
        "_get_json",
        lambda url, params=None, **kw: _payload(("NCT01000003", "ENROLLING_BY_INVITATION")),
    )

    result = ts.reverify_trials()
    assert result["expired"] == 1
    assert _row(db, row_id).url_status == "expired"


def test_network_error_never_expires(db, monkeypatch):
    import job_finder.trial_status as ts

    row_id = _seed_trial(db, "NCT01000004")
    monkeypatch.setattr(ts, "_get_json", lambda url, params=None, **kw: None)

    result = ts.reverify_trials()
    assert result == {"checked": 1, "expired": 0, "kept": 0, "errors": 1}
    row = _row(db, row_id)
    assert row.url_status == "unknown"
    # unstamped, so the next batch retries it first
    assert row.last_checked_at is None


def test_id_missing_from_a_healthy_response_is_kept(db, monkeypatch):
    import job_finder.trial_status as ts

    kept_id = _seed_trial(db, "NCT01000005")
    gone_id = _seed_trial(db, "NCT01000006")
    monkeypatch.setattr(
        ts, "_get_json", lambda url, params=None, **kw: _payload(("NCT01000005", "RECRUITING"))
    )

    result = ts.reverify_trials()
    assert result == {"checked": 2, "expired": 0, "kept": 1, "errors": 1}
    assert _row(db, kept_id).url_status == "alive"
    assert _row(db, gone_id).url_status == "unknown"


def test_statuses_map_by_nct_id_not_response_order(db, monkeypatch):
    # verified live 2026-07-14: the API returns studies in its own order
    import job_finder.trial_status as ts

    closed_id = _seed_trial(db, "NCT01000007")
    open_id = _seed_trial(db, "NCT01000008")
    monkeypatch.setattr(
        ts,
        "_get_json",
        lambda url, params=None, **kw: _payload(
            ("NCT01000008", "RECRUITING"), ("NCT01000007", "TERMINATED")
        ),
    )

    result = ts.reverify_trials()
    assert result["expired"] == 1 and result["kept"] == 1
    assert _row(db, closed_id).url_status == "expired"
    assert _row(db, open_id).url_status == "alive"


def test_request_params_and_chunking(db, monkeypatch):
    import job_finder.trial_status as ts

    for i in range(3):
        _seed_trial(db, f"NCT0200000{i}")
    monkeypatch.setattr(ts, "_CHUNK_SIZE", 2)

    captured: list[dict] = []

    def fake_get_json(url, params=None, **kw):
        assert url == "https://clinicaltrials.gov/api/v2/studies"
        captured.append(dict(params or {}))
        ids = params["filter.ids"].split(",")
        return _payload(*[(nct, "RECRUITING") for nct in ids])

    monkeypatch.setattr(ts, "_get_json", fake_get_json)
    result = ts.reverify_trials()
    assert result == {"checked": 3, "expired": 0, "kept": 3, "errors": 0}
    assert len(captured) == 2
    assert captured[0]["filter.ids"] == "NCT02000000,NCT02000001"
    assert captured[0]["pageSize"] == "2"
    assert captured[1]["filter.ids"] == "NCT02000002"
    assert captured[0]["fields"] == (
        "protocolSection.identificationModule.nctId,"
        "protocolSection.statusModule.overallStatus"
    )


def test_follows_next_page_token_within_a_chunk(db, monkeypatch):
    import job_finder.trial_status as ts

    a = _seed_trial(db, "NCT03000001")
    b = _seed_trial(db, "NCT03000002")
    page1 = _payload(("NCT03000001", "RECRUITING"))
    page1["nextPageToken"] = "TOKEN123"
    page2 = _payload(("NCT03000002", "SUSPENDED"))
    captured: list[dict] = []

    def fake_get_json(url, params=None, **kw):
        captured.append(dict(params or {}))
        return page2 if params.get("pageToken") else page1

    monkeypatch.setattr(ts, "_get_json", fake_get_json)
    result = ts.reverify_trials()
    assert len(captured) == 2
    assert captured[1]["pageToken"] == "TOKEN123"
    assert result == {"checked": 2, "expired": 1, "kept": 1, "errors": 0}
    assert _row(db, a).url_status == "alive"
    assert _row(db, b).url_status == "expired"


def test_only_visible_clinicaltrials_rows_are_checked(db, monkeypatch):
    import job_finder.trial_status as ts

    visible = _seed_trial(db, "NCT04000001")
    tombstoned = _seed_trial(db, "NCT04000002")
    session = db.get_session()
    try:
        session.get(db.ApplicationRecord, tombstoned).url_status = "expired"
        session.commit()
    finally:
        session.close()
    db.save_application(
        job_title="Not a trial", company="X",
        job_url="https://x.example/NCT04000003", source="bankrewards",
        vertical="house",
    )

    captured: list[str] = []

    def fake_get_json(url, params=None, **kw):
        captured.append(params["filter.ids"])
        return _payload(("NCT04000001", "WITHDRAWN"))

    monkeypatch.setattr(ts, "_get_json", fake_get_json)
    result = ts.reverify_trials()
    assert captured == ["NCT04000001"]
    assert result == {"checked": 1, "expired": 1, "kept": 0, "errors": 0}
    assert _row(db, visible).url_status == "expired"


def test_max_checks_caps_the_batch(db, monkeypatch):
    import job_finder.trial_status as ts

    for i in range(4):
        _seed_trial(db, f"NCT0500000{i}")

    def fake_get_json(url, params=None, **kw):
        ids = params["filter.ids"].split(",")
        return _payload(*[(nct, "RECRUITING") for nct in ids])

    monkeypatch.setattr(ts, "_get_json", fake_get_json)
    result = ts.reverify_trials(max_checks=2)
    assert result["checked"] == 2


def test_accepts_a_caller_owned_session(db, monkeypatch):
    import job_finder.trial_status as ts

    _seed_trial(db, "NCT06000001")
    monkeypatch.setattr(
        ts, "_get_json", lambda url, params=None, **kw: _payload(("NCT06000001", "COMPLETED"))
    )

    session = db.get_session()
    try:
        result = ts.reverify_trials(session)
        assert result["expired"] == 1
        # the caller's session stays open and usable
        assert session.query(db.ApplicationRecord).count() == 1
    finally:
        session.close()


class TestSchedulerRide:
    """Trial re-verification rides the tick beside the dead-link batch."""

    def _quiet_tick(self, monkeypatch) -> None:
        import job_finder.schedule as schedule
        from app.services import application_service

        monkeypatch.setattr(schedule, "due_sources", lambda now=None: [])
        monkeypatch.setattr(
            application_service,
            "check_urls",
            lambda db, ids=None, limit=100, workspace_id=None, live_only=False: {
                "checked": 0, "alive": 0, "dead": 0, "unknown": 0,
            },
        )

    def test_tick_reverifies_a_batch_of_trials(self, monkeypatch) -> None:
        self._quiet_tick(monkeypatch)

        captured: dict = {}

        def fake_reverify(db, max_checks=200):
            captured["max_checks"] = max_checks
            return {"checked": max_checks, "expired": 2, "kept": 1, "errors": 0}

        import job_finder.trial_status as ts

        monkeypatch.setattr(ts, "reverify_trials", fake_reverify)

        from app.services.scheduler_service import BoardScheduler

        sched = BoardScheduler(tick_seconds=900, initial_delay_seconds=0, reverify_batch=40)
        asyncio.run(sched.tick())
        assert captured == {"max_checks": 40}

    def test_zero_batch_never_reverifies_trials(self, monkeypatch) -> None:
        self._quiet_tick(monkeypatch)

        import job_finder.trial_status as ts

        def boom(*a, **kw):  # pragma: no cover - the assertion is that this never runs
            raise AssertionError("re-verified trials with a zero batch")

        monkeypatch.setattr(ts, "reverify_trials", boom)

        from app.services.scheduler_service import BoardScheduler

        sched = BoardScheduler(tick_seconds=900, initial_delay_seconds=0)
        assert asyncio.run(sched.tick()) == 0
