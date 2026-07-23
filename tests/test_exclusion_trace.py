"""Unit tests for the exclusion tracer itself.

Covers the machinery (not the corpus): stage ordering, first_blocker picking
the right stage, an all-pass row, a hypothetical dict row that never touches a
database, and that a not-applied stage never masks the real blocker.
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
def session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from job_finder.models.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'trace.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add(session, **kw):
    from job_finder.models.database import ApplicationRecord

    kw.setdefault("vertical", "career")
    kw.setdefault("company", "Acme")
    rec = ApplicationRecord(**kw)
    session.add(rec)
    session.flush()
    return rec


# --- stage ordering -------------------------------------------------------


def test_results_follow_canonical_stage_order(session):
    from app.services import exclusion_trace as et

    rec = _add(session, job_title="Data Engineer", location="United States", job_url="a")
    session.commit()
    results = et.trace_exclusion(
        session, row_id=rec.id, filters={"roles": ["Data Engineer"]}, lane="work"
    )
    assert [r.stage for r in results] == list(et.STAGE_ORDER)


def test_every_stage_reports_pass_applied_reason(session):
    from app.services import exclusion_trace as et

    rec = _add(session, job_title="Data Engineer", location="United States", job_url="b")
    session.commit()
    results = et.trace_exclusion(session, row_id=rec.id, filters={}, lane="work")
    for r in results:
        assert isinstance(r.passed, bool)
        assert isinstance(r.applied, bool)
        assert isinstance(r.reason, str) and r.reason
        assert isinstance(r.detail, dict)


# --- first_blocker picks the right stage ----------------------------------


def test_first_blocker_names_the_location_stage(session):
    from app.services import exclusion_trace as et

    rec = _add(session, job_title="Data Engineer",
               location="New York, United States", job_url="c")
    session.commit()
    results = et.trace_exclusion(
        session, row_id=rec.id,
        filters={"location": "Los Angeles", "roles": ["Data Engineer"]}, lane="work",
    )
    blocker = et.first_blocker(results)
    assert blocker is not None
    assert blocker.stage == "location"
    assert et.verdict(results).startswith("hidden by location")


def test_first_blocker_is_the_earliest_failing_stage(session):
    """A row that fails BOTH location and dead-link blames location (earlier)."""
    from app.services import exclusion_trace as et

    rec = _add(session, job_title="Data Engineer",
               location="New York, United States", url_status="dead", job_url="d")
    session.commit()
    results = et.trace_exclusion(
        session, row_id=rec.id,
        filters={"location": "Los Angeles", "roles": ["Data Engineer"]}, lane="work",
    )
    blocker = et.first_blocker(results)
    assert blocker.stage == "location"
    # dead-link would also fail, but it comes later and is not the culprit.
    stages = {r.stage: r for r in results}
    assert stages["dead_link"].passed is False


# --- a fully visible row --------------------------------------------------


def test_fully_visible_row_reports_all_pass(session):
    from app.services import exclusion_trace as et

    rec = _add(session, job_title="Data Engineer", location="United States", job_url="e")
    session.commit()
    results = et.trace_exclusion(
        session, row_id=rec.id,
        filters={"location": "Los Angeles", "roles": ["Data Engineer"],
                 "posted_within_days": 30}, lane="work",
    )
    assert et.first_blocker(results) is None
    assert et.verdict(results) == "visible on the board"
    for r in results:
        assert r.passed is True


def test_not_applied_stage_never_masks_the_blocker(session):
    """salary is unset (not applied) yet a later dead-link still surfaces."""
    from app.services import exclusion_trace as et

    rec = _add(session, job_title="Data Engineer", location="United States",
               url_status="expired", job_url="f")
    session.commit()
    results = et.trace_exclusion(
        session, row_id=rec.id, filters={"roles": ["Data Engineer"]}, lane="work"
    )
    stages = {r.stage: r for r in results}
    assert stages["salary"].applied is False
    assert stages["salary"].passed is True
    assert et.first_blocker(results).stage == "dead_link"


# --- hypothetical (dict) row, no DB ---------------------------------------


def test_hypothetical_row_needs_no_database():
    from app.services import exclusion_trace as et

    results = et.trace_exclusion(
        None,
        row={"title": "Staff Data Engineer", "company": "BILL", "location": "United States"},
        filters={"location": "Los Angeles", "roles": ["Staff Data Engineer"],
                 "posted_within_days": 30},
        lane="work",
    )
    assert et.first_blocker(results) is None
    assert et.verdict(results) == "visible on the board"


def test_hypothetical_row_blocked_by_location():
    from app.services import exclusion_trace as et

    results = et.trace_exclusion(
        None,
        row={"title": "Staff Data Engineer", "company": "NYCo",
             "location": "New York, United States"},
        filters={"location": "Los Angeles", "roles": ["Staff Data Engineer"]},
        lane="work",
    )
    assert et.first_blocker(results).stage == "location"


def test_hypothetical_foreign_remote_blocked_by_location():
    from app.services import exclusion_trace as et

    results = et.trace_exclusion(
        None,
        row={"title": "Data Engineer", "company": "Off",
             "location": "Remote, India", "remote_scope": "intl", "is_remote": True},
        filters={"location": "Los Angeles", "roles": ["Data Engineer"]},
        lane="work",
    )
    assert et.first_blocker(results).stage == "location"


# --- lane vocabulary ------------------------------------------------------


def test_quests_lane_ignores_work_only_stages():
    """A title that is off-lane for career must not block a side quest, because
    the quests lane does not run title/anchored-freshness/dedup/salary."""
    from app.services import exclusion_trace as et

    results = et.trace_exclusion(
        None,
        row={"title": "Dog Walker", "company": "PetCo", "location": "United States",
             "vertical": "lookafter"},
        filters={"location": "Los Angeles", "roles": ["Data Engineer"],
                 "salary_min": 999999},
        lane="quests",
    )
    stages = {r.stage: r for r in results}
    assert stages["title_match"].applied is False
    assert stages["salary"].applied is False
    assert stages["dedup"].applied is False
    assert et.first_blocker(results) is None


def test_resolve_missing_target_reports_unresolved(session):
    from app.services import exclusion_trace as et

    results = et.trace_exclusion(
        session, company="Nonexistent Co", title="Ghost Role", filters={}, lane="work"
    )
    assert len(results) == 1
    assert results[0].stage == "resolve"
    assert results[0].passed is False


def test_first_blocker_and_verdict_on_visible_hypothetical():
    from app.services import exclusion_trace as et

    results = et.trace_exclusion(
        None, row={"title": "Data Engineer", "company": "X"}, filters={}, lane="work"
    )
    assert et.first_blocker(results) is None
    assert et.verdict(results) == "visible on the board"
