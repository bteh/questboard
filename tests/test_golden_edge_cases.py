"""Golden regression: every tricky filter case from this session, frozen.

Seeds each corpus row into a temp DB and asserts trace_exclusion's verdict
matches the recorded expectation. Cases meaningful on both lanes are checked on
a career/work vertical AND a side-quest vertical, since the two lanes share the
filter vocabulary. The tracer runs the REAL production predicates, so a drift in
any filter's meaning flips the matching case and fails here.
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
sys.path.insert(0, str(Path(__file__).parent))  # so `fixtures.edge_cases` imports

from fixtures.edge_cases import DEDUP_PAIR, EDGE_CASES  # noqa: E402

# vertical to seed for each lane. "career" is the work lane; "lookafter" (pet /
# child sitting) is a real side-quest vertical.
_LANE_VERTICAL = {"work": "career", "quests": "lookafter"}


@pytest.fixture()
def session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from job_finder.models.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'golden.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _materialize_dates(row: dict) -> dict:
    """Convert the fixture's relative-date shortcuts into concrete values, so
    freshness cases are stable no matter which day the suite runs."""
    data = dict(row)
    now = datetime.now(timezone.utc)
    if "date_found_days_ago" in data:
        data["date_found"] = now - timedelta(days=data.pop("date_found_days_ago"))
    if "date_posted_epoch_days_ago" in data:
        days = data.pop("date_posted_epoch_days_ago")
        data["date_posted"] = str(int((now - timedelta(days=days)).timestamp()))
    if "date_posted_iso_days_ago" in data:
        days = data.pop("date_posted_iso_days_ago")
        data["date_posted"] = (now - timedelta(days=days)).isoformat()
    return data


def _seed(session, row: dict, vertical: str) -> int:
    from job_finder.models.database import ApplicationRecord

    data = _materialize_dates(row)
    data.setdefault("company", "Acme")
    data["vertical"] = vertical
    rec = ApplicationRecord(**data)
    session.add(rec)
    session.flush()
    return rec.id


def _assert_verdict(results, expected, case_id):
    from app.services import exclusion_trace as et

    blocker = et.first_blocker(results)
    if expected["outcome"] == "visible":
        assert blocker is None, (
            f"{case_id}: expected visible, but {blocker.stage} dropped it "
            f"({blocker.reason})"
        )
    else:
        assert blocker is not None, f"{case_id}: expected hidden at {expected['stage']}, got visible"
        assert blocker.stage == expected["stage"], (
            f"{case_id}: expected block at {expected['stage']}, got {blocker.stage} "
            f"({blocker.reason})"
        )


def _lane_case_params():
    params = []
    for case in EDGE_CASES:
        for lane in case["lanes"]:
            params.append(pytest.param(case, lane, id=f"{case['id']}::{lane}"))
    return params


@pytest.mark.parametrize("case, lane", _lane_case_params())
def test_edge_case_verdict(session, case, lane):
    from app.services import exclusion_trace as et

    row_id = _seed(session, case["row"], _LANE_VERTICAL[lane])
    session.commit()
    results = et.trace_exclusion(
        session, row_id=row_id, filters=dict(case["filters"]), lane=lane
    )
    _assert_verdict(results, case["expected"], f"{case['id']}::{lane}")


def test_cross_source_duplicate_pair(session):
    from app.services import exclusion_trace as et

    keeper_id = _seed(session, DEDUP_PAIR["keeper"], "career")
    loser_id = _seed(session, DEDUP_PAIR["loser"], "career")
    session.commit()

    keeper = et.trace_exclusion(
        session, row_id=keeper_id, filters=dict(DEDUP_PAIR["filters"]), lane="work"
    )
    loser = et.trace_exclusion(
        session, row_id=loser_id, filters=dict(DEDUP_PAIR["filters"]), lane="work"
    )
    _assert_verdict(keeper, DEDUP_PAIR["keeper_expected"], "dedup_keeper")
    _assert_verdict(loser, DEDUP_PAIR["loser_expected"], "dedup_loser")

    # The dropped copy must name the survivor, so the trace is actionable.
    blocker = et.first_blocker(loser)
    assert blocker.detail.get("kept_instead", {}).get("id") == keeper_id


def test_corpus_covers_every_session_case():
    """Guard: the corpus keeps the named cases from this session."""
    ids = {c["id"] for c in EDGE_CASES} | {DEDUP_PAIR["id"]}
    required = {
        "us_nationwide_visible",
        "multi_location_trailing_us_visible",
        "new_york_hidden_for_la",
        "foreign_remote_intl_hidden",
        "placeless_visible",
        "hourly_50_clears_60k_floor_visible",
        "session_pay_kept_visible",
        "reposted_3_days_hidden_by_3",
        "reposted_3_days_visible_by_30",
        "bare_epoch_recent_visible",
        "rfc2822_unknown_kept_saved_default",
        "dead_url_status_hidden",
        "cross_source_duplicate_pair",
    }
    missing = required - ids
    assert not missing, f"corpus is missing session cases: {sorted(missing)}"
