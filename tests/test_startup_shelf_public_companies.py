"""Public companies and old quant shops must not sit on the startup shelf.

Real case, 2026-09-22: Brian's Find Work board listed Airbnb under the
"Startups & founding" chip. company_classifier hardcoded "airbnb" in
ELITE_STARTUPS (public since Dec 2020). The known-list check runs first, so
that stamp beat every other signal, and the startup shelf predicate in
application_service treats the Elite Startup tier as proof. 21 Airbnb rows
in his database carried company_type "Elite Startup". The same list held
"figma" (public since July 2025) and eight quant/HFT firms founded decades
ago: Citadel, Jane Street, Hudson River Trading, Two Sigma, De Shaw, Jump
Trading, Tower Research, Virtu Financial.

Two fixes, both pinned here. The classifier tiers Airbnb and Figma as Big
Tech (public tech) and the quant firms as Enterprise (finance). A versioned
data repair re-stamps stored rows for exactly those ten companies and leaves
genuinely private ones (Anthropic) alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from job_finder.company_classifier import classify_company  # noqa: E402
from job_finder.models.company_tier_repair import (  # noqa: E402
    PUBLIC_COMPANY_TIER_REPAIR_NAME,
    PUBLIC_COMPANY_TIER_REPAIR_VERSION,
    repair_company_tiers,
)

QUANT_FIRMS = (
    "Citadel", "Jane Street", "Hudson River Trading", "Two Sigma",
    "De Shaw", "Jump Trading", "Tower Research", "Virtu Financial",
)
STAMP = "2026-07-01T00:00:00+00:00"


@pytest.mark.parametrize("name", ["Airbnb", "Airbnb, Inc.", "AIRBNB", "Figma"])
def test_public_tech_companies_are_big_tech(name: str) -> None:
    assert classify_company(name) == "Big Tech"


@pytest.mark.parametrize("name", QUANT_FIRMS)
def test_quant_firms_are_enterprise(name: str) -> None:
    verdict = classify_company(name)
    assert verdict == "Enterprise"
    assert verdict != "Elite Startup"


def test_anthropic_keeps_its_elite_startup_tier() -> None:
    assert classify_company("Anthropic") == "Elite Startup"


@pytest.fixture()
def engine(tmp_path):
    """Temp DB only; the desktop runtime's DB is a symlink to the live board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, company VARCHAR, source VARCHAR,"
            " vertical VARCHAR, company_type VARCHAR, funding_stage VARCHAR,"
            " total_funding VARCHAR, updated_at VARCHAR)"
        ))
    return eng


def _add(engine, **kw) -> None:
    row = {
        "company": "Airbnb", "source": "greenhouse", "vertical": "career",
        "company_type": "Elite Startup", "updated_at": STAMP,
    }
    row.update(kw)
    cols = ", ".join(row)
    binds = ", ".join(f":{k}" for k in row)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO applications ({cols}) VALUES ({binds})"), row)


def _types(engine) -> list[tuple[str, str]]:
    with engine.begin() as conn:
        return [tuple(r) for r in conn.execute(
            text("SELECT company, company_type FROM applications ORDER BY id")
        )]


def test_repair_restamps_airbnb_and_leaves_anthropic(engine) -> None:
    _add(engine)
    _add(engine, company="Airbnb, Inc.")
    _add(engine, company="AIRBNB")
    _add(engine, company="Jane Street")
    _add(engine, company="Anthropic")
    assert repair_company_tiers(engine) == 4
    assert _types(engine) == [
        ("Airbnb", "Big Tech"),
        ("Airbnb, Inc.", "Big Tech"),
        ("AIRBNB", "Big Tech"),
        ("Jane Street", "Enterprise"),
        ("Anthropic", "Elite Startup"),
    ]


def test_repair_only_touches_the_companies_that_left_the_list(engine) -> None:
    """A row tiered Elite Startup from funding heuristics has no known-list
    entry; re-judging it without its signals would collapse it to Unknown."""
    _add(engine, company="SeriesDCo", funding_stage="Series D")
    _add(engine, company="Anthropic")
    assert repair_company_tiers(engine) == 0
    assert _types(engine) == [("SeriesDCo", "Elite Startup"), ("Anthropic", "Elite Startup")]


def test_repair_does_not_reshuffle_the_board(engine) -> None:
    _add(engine)
    repair_company_tiers(engine)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT updated_at FROM applications")).scalar() == STAMP


def test_repair_records_its_version_and_a_second_run_touches_nothing(engine) -> None:
    _add(engine)
    repair_company_tiers(engine)
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT version FROM data_repairs WHERE name = :n"),
            {"n": PUBLIC_COMPANY_TIER_REPAIR_NAME},
        ).scalar()
    assert version == PUBLIC_COMPANY_TIER_REPAIR_VERSION
    _add(engine, company="Figma")
    assert repair_company_tiers(engine) == 0, "version marker should skip"
    assert _types(engine)[-1] == ("Figma", "Elite Startup")
    assert repair_company_tiers(engine, force=True) == 1


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    """Real schema on a temp file so the backend predicate can run against it.

    init_db runs the startup repairs during migration, which records the
    marker before any rows exist, so the test below runs the repair with
    force=True after inserting its rows.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOSTED_MODE", "false")
    import importlib

    database = importlib.import_module("job_finder.models.database")
    database.init_db(str(tmp_path / "job_tracker.db"))
    session = database._SessionLocal()
    yield session
    session.close()
    database._SessionLocal.remove()


def test_startup_shelf_no_longer_lists_airbnb_after_repair(db_session) -> None:
    import importlib

    database = importlib.import_module("job_finder.models.database")
    from app.services import application_service

    ApplicationRecord = database.ApplicationRecord
    db_session.add_all([
        ApplicationRecord(
            job_title="Data Platform Manager", company="Airbnb",
            location="San Francisco, CA", source="greenhouse",
            job_url="https://x/airbnb", company_type="Elite Startup",
        ),
        ApplicationRecord(
            job_title="Data Engineer", company="Anthropic",
            location="San Francisco, CA", source="greenhouse",
            job_url="https://x/anthropic", company_type="Elite Startup",
        ),
    ])
    db_session.commit()

    shelf = application_service.source_category_condition(ApplicationRecord, "startup")
    before = {r.company for r in db_session.query(ApplicationRecord).filter(shelf)}
    assert before == {"Airbnb", "Anthropic"}, "harness: both rows sit on the shelf pre-repair"

    assert repair_company_tiers(database._engine, force=True) == 1
    db_session.expire_all()

    after = {r.company for r in db_session.query(ApplicationRecord).filter(shelf)}
    assert after == {"Anthropic"}
    airbnb = db_session.query(ApplicationRecord).filter_by(company="Airbnb").one()
    assert airbnb.company_type == "Big Tech"
