"""Board fixes from the Oct 12 2026 audit of the owner's real board (394 rows).

1. Ranking: the board sorted the assistant's picks by rank number alone.
   Each assistant session inserts its ranks as global positions, so picks
   from older sessions sank: 13 "strong" rows sat below "good" and "reach"
   rows (Zscaler "Senior Manager, Data Engineering", strong, at position 30
   under a "reach" Staff Data Engineer at Cribl). The verdict tier orders
   first; rank only orders within a tier.
2. Searched roles the person never saved: refresh_work ran 18 roles (11
   saved plus 7 the assistant chose) while the board filters by the 11 saved
   ones, so ~12 rows the assistant called "good" (Senior/Staff Analytics
   Engineer at Deepgram, Polymarket, Vanta, Mercury, Rula) never showed.
   Unsaved searched roles become a pending proposal the person can accept;
   nothing writes saved roles without that click.
3. "BI" is "business intelligence": "BI Engineering, Manager" (Evercommerce)
   and "Power BI Manager" missed the saved role "Manager, Business
   Intelligence". "BIM Manager" (building information modeling) must not.
4. KD Pharma "Business Intelligence Manager (m/f/d) | Remote (Europe) |
   Full-time", location "Bexbach", reached a Los Angeles + US-remote board:
   the region lived in the title and the location named only a German town.
5. A format-only rewrite of date_posted (the Sep 22 calendar repair) threw
   away 143 of the assistant's verdicts, including its #1 pick (Capital
   Group, "Data and AI Engineering Manager"), because the posting
   fingerprint hashed the raw date text.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


SAVED_ROLES = [
    "Data Engineering Manager",
    "Senior Manager, Data Engineering",
    "Manager, Business Intelligence",
    "Staff Data Engineer",
]


@pytest.fixture()
def board_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("JOB_FINDER_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    db.add(Workspace(id="local", name="Local", slug="local", last_active_at=now, expires_at=now + timedelta(days=7)))
    db.add(
        WorkspacePreferences(
            workspace_id="local",
            roles_json=json.dumps(SAVED_ROLES),
            keywords_json="[]",
            workplace_preference="remote_friendly",
            max_days_old=45,
            preferred_places_json=json.dumps([{"label": "Los Angeles, CA"}]),
        )
    )
    db.commit()
    yield db
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


def _add(db, title: str, company: str, **fields):
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    row = ApplicationRecord(
        job_title=title,
        company=company,
        job_url=fields.pop("job_url", f"https://jobs.example/{company.replace(' ', '-').lower()}/{abs(hash(title))}"),
        location=fields.pop("location", "Los Angeles, CA"),
        state_codes=fields.pop("state_codes", ",CA,"),
        remote_scope=fields.pop("remote_scope", "us"),
        is_remote=fields.pop("is_remote", False),
        source=fields.pop("source", "greenhouse"),
        vertical="career",
        description=fields.pop("description", "Lead the data platform team."),
        date_posted=fields.pop("date_posted", now.isoformat()),
        date_confidence="exact",
        date_found=now,
        **fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _board(db, **overrides):
    from app.api.applications import list_profile_work

    kwargs = dict(
        search=None,
        location=None,
        location_strict=False,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        is_remote=None,
        founding_only=False,
        posted_within_days=None,
        found_within_days=None,
        timezone_name="UTC",
        source_category=None,
        level=None,
        sort_by="date_found",
        page=1,
        page_size=50,
        workspace=SimpleNamespace(workspace=SimpleNamespace(id="local")),
        db=db,
    )
    kwargs.update(overrides)
    return list_profile_work(**kwargs)


def _titles(db) -> list[str]:
    return [item.job_title for item in _board(db).items]


# 1. Verdict tier orders the ranked picks ------------------------------------


def test_a_strong_pick_from_an_older_session_stays_above_newer_good_and_reach_picks(board_db) -> None:
    from app.services import local_agent_service

    zscaler = _add(board_db, "Senior Manager, Data Engineering", "Zscaler")
    cribl = _add(board_db, "Staff Data Engineer", "Cribl")
    carrot = _add(board_db, "Data Engineering Manager", "Carrotfertility")

    # Session one (Sep 22) judged Zscaler strong.
    local_agent_service.set_work_fit(board_db, [{"opportunity_id": zscaler.id, "verdict": "strong", "rank": 1}])
    # Later sessions placed their own picks at the top of the global list.
    local_agent_service.agent_run_progress.set_work_fit_run_id(None)
    local_agent_service.set_work_fit(
        board_db,
        [
            {"opportunity_id": cribl.id, "verdict": "reach", "rank": 1},
            {"opportunity_id": carrot.id, "verdict": "good", "rank": 2},
        ],
    )

    titles = _titles(board_db)
    assert titles.index("Senior Manager, Data Engineering") < titles.index("Data Engineering Manager")
    assert titles.index("Data Engineering Manager") < titles.index("Staff Data Engineer")


def test_rank_still_orders_picks_inside_one_tier(board_db) -> None:
    from app.services import local_agent_service

    first = _add(board_db, "Data Engineering Manager", "Toast")
    second = _add(board_db, "Senior Manager, Data Engineering", "Carrum Health")
    local_agent_service.set_work_fit(
        board_db,
        [
            {"opportunity_id": second.id, "verdict": "strong", "rank": 2},
            {"opportunity_id": first.id, "verdict": "strong", "rank": 1},
        ],
    )
    titles = _titles(board_db)
    assert titles.index("Data Engineering Manager") < titles.index("Senior Manager, Data Engineering")


# 2. Searched roles the person never saved become a proposal ------------------


def test_unsaved_roles_from_an_assistant_refresh_become_a_pending_proposal(board_db) -> None:
    from app.services import local_agent_service

    searched = SAVED_ROLES + ["Staff Analytics Engineer", "Principal Data Engineer"]
    local_agent_service.propose_searched_roles(board_db, searched, workspace_id="local")

    pending = local_agent_service.list_role_proposals(board_db, workspace_id="local")["proposals"]
    assert len(pending) == 1
    proposed = pending[0]["proposed_roles"]
    assert proposed[: len(SAVED_ROLES)] == SAVED_ROLES
    assert {"Staff Analytics Engineer", "Principal Data Engineer"} <= set(proposed)
    # Nothing saved without the person's click.
    assert local_agent_service.career_preferences(board_db, "local")["preferences"]["roles"] == SAVED_ROLES


def test_a_refresh_that_only_searches_saved_roles_proposes_nothing(board_db) -> None:
    from app.services import local_agent_service

    local_agent_service.propose_searched_roles(
        board_db, [role.upper() for role in SAVED_ROLES], workspace_id="local"
    )
    assert local_agent_service.list_role_proposals(board_db, workspace_id="local")["proposals"] == []


def test_refresh_work_with_extra_roles_records_the_proposal(board_db, monkeypatch) -> None:
    from app import local_mcp
    from app.services import local_agent_service, pipeline_service

    monkeypatch.setattr(
        pipeline_service,
        "start_run",
        lambda **kwargs: SimpleNamespace(run_id="stub", status="pending"),
    )
    asyncio.run(local_mcp.refresh_work(roles=SAVED_ROLES + ["Staff Analytics Engineer"]))

    pending = local_agent_service.list_role_proposals(board_db, workspace_id="local")["proposals"]
    assert pending and "Staff Analytics Engineer" in pending[0]["proposed_roles"]


# 3. BI means business intelligence --------------------------------------------


@pytest.mark.parametrize("title", ["BI Engineering, Manager", "Power BI Manager", "Senior BI Manager"])
def test_bi_titles_match_a_business_intelligence_role(board_db, title) -> None:
    _add(board_db, title, "Evercommerce")
    assert title in _titles(board_db)


def test_bim_is_not_business_intelligence(board_db) -> None:
    _add(board_db, "BIM Manager", "Turner Construction")
    assert "BIM Manager" not in _titles(board_db)


# 4. A region named in the title scopes a remote posting -------------------------

KD_PHARMA = "Business Intelligence Manager (m/f/d) | Remote (Europe) | Full-time"


def test_pull_drops_a_remote_posting_whose_title_names_europe() -> None:
    from job_finder.company_classifier import location_matches_preferences

    assert location_matches_preferences(
        "Bexbach", True, preferred_states=["CA"], preferred_countries=["united states"], title=KD_PHARMA,
    ) is False
    assert location_matches_preferences(
        "Bexbach", True, preferred_states=["CA"], preferred_countries=["united states"],
        title="Business Intelligence Manager | Remote (US)",
    ) is True


def test_saved_remote_scope_reads_the_title_when_the_location_is_silent(board_db) -> None:
    from job_finder.models.database import save_application

    save_application(
        job_title=KD_PHARMA, company="KD Pharma", location="Bexbach",
        job_url="https://www.arbeitnow.com/jobs/kd-pharma/bi-manager", source="arbeitnow",
        is_remote=True, description="Lead BI.", date_posted=datetime.now(timezone.utc).isoformat(),
    )
    board_db.expire_all()
    assert KD_PHARMA not in _titles(board_db)


def test_startup_repair_rescopes_stored_rows_from_their_title(board_db) -> None:
    from sqlalchemy import create_engine

    from job_finder.models.maintenance import run_startup_repairs

    _add(board_db, KD_PHARMA, "KD Pharma", location="Bexbach", state_codes="", remote_scope="", is_remote=True, source="arbeitnow")
    assert KD_PHARMA in _titles(board_db)

    run_startup_repairs(create_engine(str(board_db.get_bind().url)))
    board_db.expire_all()
    assert KD_PHARMA not in _titles(board_db)


# 5. A format-only date rewrite keeps the verdict ---------------------------------


def _legacy_content_hash(record) -> str:
    payload = "\n".join(
        str(value or "")
        for value in (
            record.job_title, record.company, record.location, record.description,
            record.date_posted, record.job_url, record.work_type, record.remote_scope,
            record.salary_min, record.salary_max, record.salary_min_annualized,
            record.salary_max_annualized,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_reformatting_the_posted_date_keeps_the_assistants_verdict(board_db) -> None:
    from app.services import local_agent_service
    from job_finder.tools.scrapers._utils import normalize_posted_date

    row = _add(board_db, "Data and AI Engineering Manager", "Capital Group", source="indeed",
               date_posted="Mon, 14 Sep 2026 09:00:00 +0000")
    local_agent_service.set_work_fit(board_db, [{"opportunity_id": row.id, "verdict": "strong", "rank": 1}])

    row.date_posted = normalize_posted_date(row.date_posted)
    assert row.date_posted != "Mon, 14 Sep 2026 09:00:00 +0000"
    board_db.commit()

    profile_hash = local_agent_service.fit_profile_hash(board_db)
    assert local_agent_service.fit_review_state(row, profile_hash)["current"] is True


def test_a_real_posting_change_still_invalidates_the_verdict(board_db) -> None:
    from app.services import local_agent_service

    row = _add(board_db, "Data Engineering Manager", "Capital Group", date_posted="2026-09-14T09:00:00")
    local_agent_service.set_work_fit(board_db, [{"opportunity_id": row.id, "verdict": "strong", "rank": 1}])
    row.date_posted = "2026-10-10T09:00:00"
    row.description = "Now a director role with a different team."
    board_db.commit()

    profile_hash = local_agent_service.fit_profile_hash(board_db)
    assert local_agent_service.fit_review_state(row, profile_hash)["reason"] == "posting_changed"


def test_verdicts_stamped_with_the_old_fingerprint_stay_current(board_db) -> None:
    from app.services import local_agent_service

    row = _add(board_db, "Data Engineering Manager", "Toast", date_posted="2026-10-01T12:00:00")
    profile_hash = local_agent_service.fit_profile_hash(board_db)
    row.agent_fit_json = json.dumps({
        "rank": 1, "verdict": "strong", "why": "", "caveat": "", "run_id": "old",
        "at": "2026-10-01T12:00:00Z", "content_hash": _legacy_content_hash(row),
        "profile_hash": profile_hash, "schema_version": 1,
    })
    board_db.commit()
    assert local_agent_service.fit_review_state(row, profile_hash)["current"] is True
