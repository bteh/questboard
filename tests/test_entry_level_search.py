"""The entry path through the level filter, the board chip and staffing.

Real case (Oct 8 2026): a seeker who lost an IT job saved "IT Support
Specialist" as his current title and looked for help desk, IT support and
analyst roles. A "Help Desk Technician I" posting must reach his board, an
"Entry level" chip must count and narrow to entry rows, and agency
contract-to-hire postings (Robert Half, TEKsystems, Insight Global, Apex) must
come back when he turns staffing agencies on.
"""

from __future__ import annotations

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

from job_finder.pipeline import (  # noqa: E402
    JobFinderPipeline,
    _filter_jobs_by_level,
    _resolve_filter_settings,
)

ENTRY_IT_TITLES = [
    "Help Desk Technician I",
    "Junior Systems Administrator",
    "IT Support Specialist",
    "Service Desk Analyst - Tier 1",
    "Desktop Support Technician",
    "Associate Data Analyst",
]


@pytest.mark.parametrize("strictness", ["loose", "balanced", "strict"])
def test_it_support_current_title_keeps_entry_it_roles(strictness: str) -> None:
    kept = _filter_jobs_by_level(
        [{"title": title} for title in ENTRY_IT_TITLES],
        {"current_title": "IT Support Specialist"},
        filters=_resolve_filter_settings({"filters": {"strictness": strictness}}),
        target_roles=["IT Support Specialist", "Help Desk Technician"],
    )
    assert [job["title"] for job in kept] == ENTRY_IT_TITLES


def test_entry_seeker_keeps_entry_posting_the_level_map_rates_higher() -> None:
    """ "Consultant" maps to level 3, so strict (entry + 1) dropped it even
    though the title says entry level."""
    jobs = [
        {"title": "IT Consultant - Entry Level"},
        {"title": "IT Consultant", "description": "Requires 6+ years of experience."},
    ]
    kept = _filter_jobs_by_level(
        jobs,
        {"current_title": "", "current_level": "entry"},
        filters=_resolve_filter_settings({"filters": {"strictness": "strict"}}),
    )
    assert [job["title"] for job in kept] == ["IT Consultant - Entry Level"]


def test_entry_rescue_is_only_for_entry_seekers() -> None:
    kept = _filter_jobs_by_level(
        [{"title": "Junior Systems Administrator"}],
        {"current_title": "IT Director"},
        filters=_resolve_filter_settings(None),
    )
    assert kept == []


@pytest.mark.parametrize("company", ["Robert Half", "TEKsystems", "Insight Global", "Apex Systems"])
def test_include_staffing_agencies_keeps_contract_to_hire_postings(company: str) -> None:
    job = {"title": "Help Desk Technician", "company": company, "url": "http://x"}
    pipe = JobFinderPipeline(llm=None, profile=None)
    pipe.config = {"search_settings": {"exclude_staffing_agencies": True}}
    assert pipe.filter_staffing_agencies([job]) == []
    pipe.config = {"search_settings": {"exclude_staffing_agencies": False}}
    assert pipe.filter_staffing_agencies([job]) == [job]


def test_workspace_staffing_choice_reaches_the_pull_config() -> None:
    from app.schemas.workspace import WorkspacePreferences
    from app.services.workspace_service import build_pipeline_config_override

    prefs = WorkspacePreferences(roles=["Help Desk Technician"], exclude_staffing_agencies=False)
    config = build_pipeline_config_override(prefs, "local")
    assert config["search_settings"]["exclude_staffing_agencies"] is False


BOARD_ROWS = [
    ("Help Desk Technician I", "Acme Health", "Reset passwords and image laptops."),
    ("IT Support Specialist", "Westside Clinic", "This is an entry-level role. 0-2 years."),
    ("IT Support Specialist", "Harbor Bank", "Requires 5+ years of experience in IT support."),
    ("Senior IT Support Specialist", "Pacific Labs", "Mentor the help desk team."),
    ("Help Desk Technician", "Robert Half", "Contract-to-hire. 1+ year of help desk experience."),
]


@pytest.fixture()
def board_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    db.add(Workspace(id="local", name="Local", slug="local", last_active_at=now, expires_at=now + timedelta(days=7)))
    db.add(
        WorkspacePreferences(
            workspace_id="local",
            roles_json=json.dumps(["IT Support Specialist", "Help Desk Technician"]),
            keywords_json=json.dumps([]),
            workplace_preference="remote_friendly",
            max_days_old=45,
            current_title="IT Support Specialist",
        )
    )
    db.add_all(
        [
            ApplicationRecord(
                job_title=title,
                company=company,
                description=description,
                job_url=f"https://jobs.example/{i}",
                location="Los Angeles, CA",
                state_codes=",CA,",
                remote_scope="us",
                is_remote=False,
                source="greenhouse",
                vertical="career",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            )
            for i, (title, company, description) in enumerate(BOARD_ROWS)
        ]
    )
    db.commit()
    yield db
    generator.close()


def _call(db, **overrides):
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
        page_size=24,
        workspace=SimpleNamespace(workspace=SimpleNamespace(id="local")),
        db=db,
    )
    kwargs.update(overrides)
    return list_profile_work(**kwargs)


def test_board_keeps_help_desk_technician_one_for_it_support_title(board_db) -> None:
    titles = [item.job_title for item in _call(board_db).items]
    assert "Help Desk Technician I" in titles


def test_entry_chip_counts_and_narrows(board_db) -> None:
    response = _call(board_db)
    assert response.levels["entry"] == 2
    narrowed = _call(board_db, level="entry")
    assert {(item.job_title, item.company) for item in narrowed.items} == {
        ("Help Desk Technician I", "Acme Health"),
        ("IT Support Specialist", "Westside Clinic"),
    }
    assert narrowed.levels["entry"] == 2


def test_staffing_toggle_brings_agency_rows_into_the_entry_chip(board_db) -> None:
    from app.models.workspace import WorkspacePreferences

    prefs = board_db.query(WorkspacePreferences).filter_by(workspace_id="local").one()
    prefs.exclude_staffing_agencies = False
    board_db.commit()
    narrowed = _call(board_db, level="entry")
    assert "Robert Half" in {item.company for item in narrowed.items}
    assert narrowed.levels["entry"] == 3
