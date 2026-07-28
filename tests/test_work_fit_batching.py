"""Rankings must be able to land in batches, so a slow run keeps its work.

Real failure, 2026-07-28: "Claude Code ran past 300s and was stopped." The
progress trail showed exactly where it died:

    00:50:08  read resume
    00:51:08  sharpened roles          (60s)
    00:51:12  started the pull
    00:52:06  waiting on sources x8
    00:52:08  pulled the shortlist
              ... killed at 00:55:05, set_work_fit never called

The scrape had finished fine (230 jobs in 110s). Everything after was the
assistant composing one enormous set_work_fit call covering ~50 jobs, and
because that write is all-or-nothing the timeout threw away the entire run.
The last rankings that landed were from a night when the board yielded 29
candidates; the board grew past what one write can finish in time.

So set_work_fit accepts batches. The catch is that it CLEARS previous
verdicts, which is what keeps the board showing one run rather than a pile of
stale ones. Clearing on every batch would leave only the last batch. The run
already announces itself (the app clears the progress trail when it launches
the assistant), so the first write of a run clears and the rest append. The
assistant needs no new flag it could get wrong.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


@pytest.fixture()
def work_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{data_dir / 'jobs.db'}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from job_finder.models.database import ApplicationRecord

    init_db(str(data_dir / "jobs.db"))
    db = next(get_db())
    now = datetime.now(timezone.utc)
    db.add_all([
        ApplicationRecord(
            job_title=f"Data Engineering Manager {i}",
            company=f"Co {i}",
            job_url=f"https://example.com/{i}",
            source="Greenhouse",
            vertical="career",
            date_found=now - timedelta(minutes=i),
        )
        for i in range(6)
    ])
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def service(work_db):
    from app.services import local_agent_service

    return local_agent_service


def _ids(db):
    from job_finder.models.database import ApplicationRecord

    return [r.id for r in db.query(ApplicationRecord).order_by(ApplicationRecord.id).all()]


def _verdicts(db):
    from job_finder.models.database import ApplicationRecord

    out = {}
    for row in db.query(ApplicationRecord).all():
        if row.agent_fit_json:
            out[row.id] = json.loads(row.agent_fit_json)["verdict"]
    return out


def test_a_second_batch_keeps_the_first(work_db, service):
    """The whole point: a run that dies after batch two still has batches one
    and two on the board."""
    ids = _ids(work_db)
    service.set_work_fit(work_db, [{"opportunity_id": ids[0], "verdict": "strong"}])
    service.set_work_fit(work_db, [{"opportunity_id": ids[1], "verdict": "good"}])

    assert _verdicts(work_db) == {ids[0]: "strong", ids[1]: "good"}


def test_a_new_run_clears_the_previous_one(work_db, service):
    """Otherwise yesterday's verdicts sit next to today's with no way to tell
    them apart."""
    from app.services import agent_run_progress

    ids = _ids(work_db)
    service.set_work_fit(work_db, [{"opportunity_id": ids[0], "verdict": "strong"}])

    agent_run_progress.clear()  # what POST /agent/run does
    service.set_work_fit(work_db, [{"opportunity_id": ids[1], "verdict": "reach"}])

    assert _verdicts(work_db) == {ids[1]: "reach"}


def test_batches_within_one_run_share_a_run_id(work_db, service):
    from job_finder.models.database import ApplicationRecord

    ids = _ids(work_db)
    service.set_work_fit(work_db, [{"opportunity_id": ids[0], "verdict": "strong"}])
    service.set_work_fit(work_db, [{"opportunity_id": ids[1], "verdict": "good"}])

    runs = {
        json.loads(r.agent_fit_json)["run_id"]
        for r in work_db.query(ApplicationRecord).all()
        if r.agent_fit_json
    }
    assert len(runs) == 1, "one run's batches must read as one run"


def test_re_scoring_a_row_in_a_later_batch_updates_it(work_db, service):
    ids = _ids(work_db)
    service.set_work_fit(work_db, [{"opportunity_id": ids[0], "verdict": "reach"}])
    service.set_work_fit(work_db, [{"opportunity_id": ids[0], "verdict": "strong"}])

    assert _verdicts(work_db) == {ids[0]: "strong"}


def test_a_batch_matching_nothing_still_does_not_wipe_the_board(work_db, service):
    """Held over from the single-write behavior: stale or invented ids must
    never cost a good run its verdicts."""
    ids = _ids(work_db)
    service.set_work_fit(work_db, [{"opportunity_id": ids[0], "verdict": "strong"}])
    out = service.set_work_fit(work_db, [{"opportunity_id": 999_999, "verdict": "good"}])

    assert out["applied"] == 0
    assert _verdicts(work_db) == {ids[0]: "strong"}
