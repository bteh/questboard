"""Rows tiered "Early Startup" by their arrival board get re-judged.

BuiltIn was registered as a startup board, and classify_company uses the
source category as a last-resort tier signal, so companies with no stronger
signal were stamped Early Startup for arriving via BuiltIn. Found 2026-07-28:
19 live rows, including CDW, a Fortune 500 IT reseller. The category fix
stops new ones; this repair re-judges the stored rows with the corrected
category, so only companies some stronger signal actually supports keep a
tier.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.models.company_tier_repair import (  # noqa: E402
    COMPANY_TIER_REPAIR_NAME,
    COMPANY_TIER_REPAIR_VERSION,
    repair_company_tiers,
)

STAMP = "2026-07-01T00:00:00+00:00"


@pytest.fixture()
def engine(tmp_path):
    """Temp DB only; the desktop runtime's DB is a symlink to the live board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, company VARCHAR, source VARCHAR,"
            " vertical VARCHAR, company_type VARCHAR, updated_at VARCHAR)"
        ))
    return eng


def _add(engine, **kw):
    row = {
        "company": "CDW", "source": "builtin", "vertical": "career",
        "company_type": "Early Startup", "updated_at": STAMP,
    }
    row.update(kw)
    cols = ", ".join(row)
    binds = ", ".join(f":{k}" for k in row)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO applications ({cols}) VALUES ({binds})"), row)


def _types(engine):
    with engine.begin() as conn:
        return [r[0] for r in conn.execute(
            text("SELECT company_type FROM applications ORDER BY id")
        )]


def test_the_cdw_case_loses_its_startup_tier(engine):
    """A Fortune 500 IT reseller was Early Startup because of which board it
    arrived on. With the board no longer startup-typed, no signal supports the
    tier and it must not survive."""
    _add(engine)
    assert repair_company_tiers(engine) == 1
    assert _types(engine) != ["Early Startup"]


def test_a_known_big_company_gets_its_real_tier(engine):
    _add(engine, company="Netflix")
    repair_company_tiers(engine)
    assert _types(engine) == ["FAANG+"]


def test_rows_from_genuinely_startup_boards_keep_their_tier(engine):
    """workatastartup is still a startup board; its tier signal was honest."""
    _add(engine, company="SomeTinyCo", source="workatastartup")
    assert repair_company_tiers(engine) == 0
    assert _types(engine) == ["Early Startup"]


def test_rows_with_other_types_are_untouched(engine):
    _add(engine, company="Netflix", company_type="FAANG+")
    assert repair_company_tiers(engine) == 0


def test_the_repair_does_not_reshuffle_the_board(engine):
    _add(engine)
    repair_company_tiers(engine)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT updated_at FROM applications")).scalar() == STAMP


def test_a_second_run_is_a_no_op(engine):
    _add(engine)
    repair_company_tiers(engine)
    _add(engine, company="Order.co")
    assert repair_company_tiers(engine) == 0, "version marker should skip"
    assert repair_company_tiers(engine, force=True) == 1


def test_the_marker_records_the_version(engine):
    _add(engine)
    repair_company_tiers(engine)
    with engine.begin() as conn:
        v = conn.execute(
            text("SELECT version FROM data_repairs WHERE name = :n"),
            {"n": COMPANY_TIER_REPAIR_NAME},
        ).scalar()
    assert v == COMPANY_TIER_REPAIR_VERSION


def test_an_empty_database_does_not_crash(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert repair_company_tiers(eng) == 0
