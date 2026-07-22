from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
def local_agent_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume
    from job_finder.models.database import ApplicationRecord, ScrapeRunRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)

    configured = Workspace(
        id="configured",
        name="Configured",
        slug="configured",
        last_active_at=now - timedelta(hours=2),
        expires_at=now + timedelta(days=7),
    )
    empty_newer = Workspace(
        id="empty-newer",
        name="Empty",
        slug="empty-newer",
        last_active_at=now,
        expires_at=now + timedelta(days=7),
    )
    db.add_all([configured, empty_newer])
    db.add(
        WorkspacePreferences(
            workspace_id="configured",
            roles_json=json.dumps(["Data Engineering Manager"]),
            keywords_json=json.dumps(["data platform", "Snowflake"]),
            preferred_places_json=json.dumps(
                [
                    {
                        "label": "Los Angeles, CA",
                        "kind": "city",
                        "match_scope": "city",
                        "city": "Los Angeles",
                        "region": "California",
                        "country": "United States",
                        "country_code": "us",
                    }
                ]
            ),
            workplace_preference="remote_friendly",
            max_days_old=14,
            current_level="manager",
        )
    )
    db.add(WorkspacePreferences(workspace_id="empty-newer"))
    db.add(
        WorkspaceResume(
            workspace_id="configured",
            original_filename="resume.pdf",
            parse_status="parsed",
            file_sha256="a" * 64,
            extracted_text="Data engineering leader with Snowflake and Python experience.",
            updated_at=now - timedelta(hours=1),
        )
    )

    db.add_all(
        [
            ApplicationRecord(
                job_title="Director of Data Engineering",
                company="Local Co",
                location="Los Angeles, CA",
                state_codes=",CA,",
                remote_scope="us",
                job_url="https://local.example/jobs/data",
                source="Greenhouse",
                description="Lead a data platform using Snowflake and Python.",
                vertical="career",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
                last_seen_at=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Europe Co",
                location="Remote (EU only)",
                remote_scope="intl",
                is_remote=True,
                work_type="remote",
                job_url="https://eu.example/jobs/data",
                source="Lever",
                description="Manage a European data platform team.",
                vertical="career",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Product Manager",
                company="Product Co",
                location="Los Angeles, CA",
                state_codes=",CA,",
                job_url="https://product.example/jobs/pm",
                source="Ashby",
                description="Own the roadmap.",
                vertical="career",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Paid software interview",
                company="Research Studio",
                location="Los Angeles, CA",
                state_codes=",CA,",
                job_url="https://research.example/study",
                source="Research Studio",
                description="Share opinions in a 60 minute session.",
                vertical="study",
                first_quest_ok=True,
                date_found=now,
            ),
            ScrapeRunRecord(
                source="Greenhouse",
                vertical="career",
                started_at=now,
                finish_reason="ok",
                rows_found=4,
            ),
        ]
    )
    db.commit()
    yield db
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


def test_profile_resolution_prefers_the_workspace_with_a_resume(local_agent_db) -> None:
    from app.services import local_agent_service

    profile = local_agent_service.career_preferences(local_agent_db)
    assert profile["workspace_id"] == "configured"
    assert profile["preferences"]["roles"] == ["Data Engineering Manager"]
    assert profile["resume"]["available"] is True
    assert profile["raw_resume_returned"] is False

    from app.services import resume_consent

    # career_preferences must never leak resume TEXT, only the availability flag
    # ("leader with Snowflake" is a phrase unique to the extracted resume text,
    # not the saved keywords).
    assert "leader with Snowflake" not in json.dumps(profile)

    # resume text is gated: refused until a person grants consent
    assert local_agent_service.resume_for_matching(local_agent_db)["available"] is False
    resume_consent.grant(profile["workspace_id"])
    resume = local_agent_service.resume_for_matching(local_agent_db)
    assert resume["available"] is True
    assert "Snowflake" in resume["resume_text"]


def test_work_search_applies_saved_location_and_excludes_foreign_remote(local_agent_db) -> None:
    from app.services import local_agent_service

    payload = local_agent_service.search_work(
        local_agent_db,
        queries=["Data Engineering"],
        page_size=20,
    )
    assert [row["organization"] for row in payload["results"]] == ["Local Co"]
    assert payload["filters_applied"]["location"] == "Los Angeles, CA"
    assert payload["ranking_owner"] == "connected_agent"
    assert payload["questboard_funded_ai"] is False
    assert payload["results"][0]["retrieval"]["is_fit_assessment"] is False


def test_work_search_rejects_description_only_role_matches(local_agent_db) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    local_agent_db.add(
        ApplicationRecord(
            job_title="Project Manager",
            company="False Positive Co",
            location="Los Angeles, CA",
            state_codes=",CA,",
            remote_scope="us",
            job_url="https://false-positive.example/jobs/project",
            source="Greenhouse",
            description="Partners closely with the Data Engineering Manager.",
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        )
    )
    local_agent_db.commit()

    payload = local_agent_service.search_work(
        local_agent_db,
        queries=["Data Engineering Manager"],
        page_size=20,
    )
    assert "False Positive Co" not in {
        row["organization"] for row in payload["results"]
    }


def test_role_family_match_rejects_conflicting_occupations() -> None:
    from app.services.local_agent_service import _title_is_in_lane

    # Primary role-family match.
    assert _title_is_in_lane(
        "Senior Engineering Manager, Data Engineering", ["Data Engineering Manager"]
    )
    # An occupation conflict the query doesn't share disqualifies the title.
    assert not _title_is_in_lane("Lead Product Manager, Data Platform", ["Data Platform Lead"])
    assert not _title_is_in_lane(
        "Senior Manager, Clinical Engineering & Data Analytics", ["Analytics Engineering Manager"]
    )


def test_title_filter_keeps_adjacent_roles_for_the_agent_to_judge() -> None:
    # Retrieval is recall-first: adjacent in-lane roles survive so the agent
    # can rank or skip them; only bare-seniority overlaps and off-lane roles drop.
    from app.services.local_agent_service import _title_is_in_lane

    q = ["Data Engineering Manager"]
    assert _title_is_in_lane("Analytics Engineering Manager", q)  # shares "engineer"
    assert _title_is_in_lane("Head of Data Platform", q)  # shares "data"
    assert _title_is_in_lane("Staff Data Engineer", q)  # shares "data"/"engineer"
    assert not _title_is_in_lane("Office Manager", q)  # only shares the seniority word
    assert not _title_is_in_lane("Registered Nurse", q)  # off lane


def test_remote_only_profile_recovers_jurisdiction_from_the_same_resume(
    local_agent_db,
) -> None:
    from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume
    from app.services import local_agent_service

    configured_preferences = (
        local_agent_db.query(WorkspacePreferences)
        .filter(WorkspacePreferences.workspace_id == "configured")
        .one()
    )
    configured_preferences.preferred_places_json = json.dumps(
        [{"label": "Remote", "kind": "manual", "country": "", "country_code": ""}]
    )
    now = datetime.now(timezone.utc)
    local_agent_db.add(
        Workspace(
            id="same-resume-sibling",
            name="Prior local workspace",
            slug="same-resume-sibling",
            last_active_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=7),
        )
    )
    local_agent_db.add(
        WorkspacePreferences(
            workspace_id="same-resume-sibling",
            preferred_places_json=json.dumps(
                [
                    {
                        "label": "Los Angeles, CA",
                        "kind": "city",
                        "city": "Los Angeles",
                        "region": "California",
                        "country": "United States",
                        "country_code": "US",
                    }
                ]
            ),
        )
    )
    local_agent_db.add(
        WorkspaceResume(
            workspace_id="same-resume-sibling",
            original_filename="resume.pdf",
            parse_status="parsed",
            file_sha256="a" * 64,
            extracted_text="Same resume in the prior local session.",
            updated_at=now - timedelta(days=1),
        )
    )
    local_agent_db.commit()

    _, location, _, _, _ = local_agent_service._saved_search_defaults(
        local_agent_db, "configured"
    )
    assert location == "Los Angeles, CA"


def test_work_search_collapses_cross_source_title_duplicates(local_agent_db) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    local_agent_db.add_all(
        [
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Duplicate Co",
                location="Los Angeles, CA",
                state_codes=",CA,",
                remote_scope="us",
                job_url="https://boards.greenhouse.io/duplicate/jobs/1",
                source="Greenhouse",
                vertical="career",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager (Remote)",
                company="duplicate co",
                location="United States",
                remote_scope="us",
                is_remote=True,
                work_type="remote",
                job_url="https://aggregator.example/duplicate/1",
                source="Aggregator",
                vertical="career",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now - timedelta(minutes=1),
            ),
        ]
    )
    local_agent_db.commit()

    payload = local_agent_service.search_work(
        local_agent_db,
        queries=["Data Engineering Manager"],
        page_size=20,
    )
    duplicates = [
        row for row in payload["results"] if row["organization"].lower() == "duplicate co"
    ]
    assert len(duplicates) == 1
    assert duplicates[0]["source"]["name"] == "Greenhouse"
    assert payload["freshness_filter_summary"]["duplicate_records_excluded"] == 1


def test_profile_work_api_returns_application_cards_for_the_active_profile(
    local_agent_db,
) -> None:
    from app.api.applications import list_profile_work
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    local_agent_db.add(
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company="Profile Match Co",
            location="Los Angeles, CA",
            state_codes=",CA,",
            remote_scope="us",
            job_url="https://profile-match.example/jobs/data",
            source="Greenhouse",
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        )
    )
    local_agent_db.commit()

    response = list_profile_work(
        search=None,
        location=None,
        location_strict=False,
        salary_min=None,
        salary_max=None,
        is_remote=None,
        posted_within_days=None,
        source_category=None,
        page=1,
        page_size=24,
        workspace=SimpleNamespace(workspace=SimpleNamespace(id="configured")),
        db=local_agent_db,
    )
    assert response.profile_configured is True
    assert response.resume_available is True
    assert response.jurisdiction_configured is True
    assert [item.company for item in response.items] == ["Profile Match Co"]
    assert response.ranking_owner == "connected_agent"


def test_work_search_enforces_fuzzy_freshness_without_hiding_default_unknowns(
    local_agent_db,
) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    local_agent_db.add_all(
        [
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Known Stale Co",
                location="Los Angeles, CA",
                state_codes=",CA,",
                remote_scope="us",
                job_url="https://stale.example/jobs/data",
                source="BuiltIn",
                vertical="career",
                date_posted="Reposted 25 Days Ago",
                date_confidence="fuzzy",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Unknown Date Co",
                location="Los Angeles, CA",
                state_codes=",CA,",
                remote_scope="us",
                job_url="https://unknown.example/jobs/data",
                source="BuiltIn",
                vertical="career",
                date_posted="",
                date_confidence="missing",
                date_found=now,
            ),
        ]
    )
    local_agent_db.commit()

    saved_default = local_agent_service.search_work(
        local_agent_db,
        queries=["Data Engineering Manager"],
        page_size=20,
    )
    organizations = {row["organization"] for row in saved_default["results"]}
    assert "Known Stale Co" not in organizations
    assert "Unknown Date Co" in organizations
    assert saved_default["filters_applied"]["posted_within_days"] == 14
    assert saved_default["freshness_filter_summary"]["known_stale_excluded"] == 1

    explicit = local_agent_service.search_work(
        local_agent_db,
        queries=["Data Engineering Manager"],
        posted_within_days=14,
        page_size=20,
    )
    explicit_organizations = {row["organization"] for row in explicit["results"]}
    assert "Known Stale Co" not in explicit_organizations
    assert "Unknown Date Co" not in explicit_organizations
    assert explicit["filters_applied"]["unknown_freshness_policy"] == "exclude"


def test_side_quest_search_never_uses_the_resume(local_agent_db) -> None:
    from app.services import local_agent_service

    payload = local_agent_service.search_side_quests(
        local_agent_db,
        kinds=["think"],
        location="Los Angeles",
        near_me_only=True,
    )
    assert payload["resume_used"] is False
    assert [row["organization"] for row in payload["results"]] == ["Research Studio"]


def test_opportunity_detail_receipt_status_and_source_health(local_agent_db) -> None:
    from app.services import local_agent_service

    found = local_agent_service.search_work(
        local_agent_db, queries=["Director of Data"], page_size=5
    )["results"][0]
    detail = local_agent_service.get_opportunity(
        local_agent_db, found["opportunity_id"]
    )
    assert detail["source"]["url"] == "https://local.example/jobs/data"
    assert len(detail["content_hash"]) == 64
    assert detail["description_is_untrusted_source_content"] is True

    updated = local_agent_service.set_opportunity_status(
        local_agent_db, found["opportunity_id"], "clipped", "Review tomorrow"
    )
    assert updated["status"] == "clipped"
    assert updated["external_action_performed"] is False

    health = local_agent_service.source_status(local_agent_db)
    assert health["sources"][0]["source"] == "Greenhouse"
    assert health["questboard_funded_ai"] is False


def test_builtin_finalist_is_hydrated_on_demand(local_agent_db) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    row = ApplicationRecord(
        job_title="Data Engineering Manager",
        company="Hydrated Co",
        location="United States",
        remote_scope="us",
        job_url="https://builtin.com/job/data-engineering-manager/123",
        source="builtin",
        description="",
        vertical="career",
    )
    local_agent_db.add(row)
    local_agent_db.commit()
    with patch(
        "job_finder.tools.scrapers.builtin.fetch_builtin_detail",
        return_value={
            "description": "Lead engineers and build reliable Snowflake pipelines.",
            "date_posted": "Posted 2 Hours Ago",
            "date_confidence": "fuzzy",
            "direct_application_url": "https://job-boards.greenhouse.io/hydrated/jobs/123",
        },
    ):
        detail = local_agent_service.get_opportunity(local_agent_db, row.id)

    assert detail["detail_resolution"] == "live_source_page"
    assert "Snowflake" in detail["description"]
    assert detail["freshness"]["source_posted_at"] == "Posted 2 Hours Ago"
    assert detail["source"]["direct_application_url"].startswith(
        "https://job-boards.greenhouse.io/"
    )


def test_local_mcp_exposes_the_two_product_workflows() -> None:
    from app.local_mcp import mcp

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {
        "search_work",
        "search_side_quests",
        "read_resume_for_matching",
        "get_career_preferences",
        "set_career_preferences",
        "refresh_work",
        "get_source_status",
        "set_opportunity_status",
    }.issubset(names)


def test_set_career_preferences_saves_and_preserves_other_prefs(local_agent_db) -> None:
    from app.services import local_agent_service

    result = local_agent_service.set_career_preferences(
        local_agent_db,
        roles=["Head of Data Platform", "AI Platform Lead"],
        keywords=["dbt", "lakehouse"],
    )
    assert result["saved"] is True
    assert result["external_action_performed"] is False

    prefs = local_agent_service.career_preferences(local_agent_db)["preferences"]
    assert prefs["roles"] == ["Head of Data Platform", "AI Platform Lead"]
    assert prefs["keywords"] == ["dbt", "lakehouse"]
    # The location and workplace the person set stay untouched.
    assert prefs["workplace_preference"] == "remote_friendly"
    assert prefs["preferred_places"], "saved location must survive a roles update"


def test_set_career_preferences_leaves_omitted_field_unchanged(local_agent_db) -> None:
    from app.services import local_agent_service

    local_agent_service.set_career_preferences(local_agent_db, roles=["Data Ops Manager"])

    prefs = local_agent_service.career_preferences(local_agent_db)["preferences"]
    assert prefs["roles"] == ["Data Ops Manager"]
    # keywords were not passed, so the seeded ones remain.
    assert prefs["keywords"] == ["data platform", "Snowflake"]


def test_set_career_preferences_requires_at_least_one_field(local_agent_db) -> None:
    import pytest as _pytest

    from app.services import local_agent_service

    with _pytest.raises(ValueError):
        local_agent_service.set_career_preferences(local_agent_db)


def test_set_career_preferences_refuses_to_clear_all_intent(local_agent_db) -> None:
    import pytest as _pytest

    from app.services import local_agent_service

    # Empty lists (or whitespace-only) would wipe the saved intent and starve
    # Find Work; the tool must refuse and leave the saved roles untouched.
    with _pytest.raises(ValueError):
        local_agent_service.set_career_preferences(local_agent_db, roles=[], keywords=[])
    with _pytest.raises(ValueError):
        local_agent_service.set_career_preferences(local_agent_db, roles=["  "], keywords=[])

    prefs = local_agent_service.career_preferences(local_agent_db)["preferences"]
    assert prefs["roles"] == ["Data Engineering Manager"]
    assert prefs["keywords"] == ["data platform", "Snowflake"]


def test_set_work_fit_writes_verdicts_and_replaces_prior(local_agent_db) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    db = local_agent_db
    ids = [
        r.id
        for r in db.query(ApplicationRecord)
        .filter(ApplicationRecord.vertical == "career")
        .order_by(ApplicationRecord.id)
        .all()
    ]

    out = local_agent_service.set_work_fit(
        db,
        [
            {"opportunity_id": ids[0], "rank": 1, "verdict": "strong", "why": "Exact stack.", "caveat": "Confirm remote."},
            {"opportunity_id": ids[1], "verdict": "skip", "why": "EU only."},
        ],
    )
    assert out["applied"] == 2
    assert out["external_action_performed"] is False

    fit0 = json.loads(db.query(ApplicationRecord).get(ids[0]).agent_fit_json)
    assert fit0["verdict"] == "strong" and fit0["rank"] == 1 and "Exact" in fit0["why"]

    # A second run replaces the prior verdicts (latest-run-only on the board).
    out2 = local_agent_service.set_work_fit(
        db, [{"opportunity_id": ids[2], "rank": 1, "verdict": "good", "why": "Now this one."}]
    )
    assert out2["applied"] == 1
    assert not db.query(ApplicationRecord).get(ids[0]).agent_fit_json  # cleared
    assert json.loads(db.query(ApplicationRecord).get(ids[2]).agent_fit_json)["verdict"] == "good"


def test_set_work_fit_rejects_bad_verdict(local_agent_db) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    db = local_agent_db
    rid = db.query(ApplicationRecord).filter(ApplicationRecord.vertical == "career").first().id
    with pytest.raises(ValueError):
        local_agent_service.set_work_fit(db, [{"opportunity_id": rid, "verdict": "amazing"}])


def test_set_work_fit_does_not_wipe_prior_when_no_ids_match(local_agent_db) -> None:
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    db = local_agent_db
    ids = [
        r.id
        for r in db.query(ApplicationRecord)
        .filter(ApplicationRecord.vertical == "career")
        .order_by(ApplicationRecord.id)
        .all()
    ]
    local_agent_service.set_work_fit(db, [{"opportunity_id": ids[0], "rank": 1, "verdict": "strong", "why": "Keep me."}])

    # A run whose ids match no row must NOT clear the prior good run's verdicts.
    out = local_agent_service.set_work_fit(db, [{"opportunity_id": 999999, "verdict": "good", "why": "ghost"}])
    assert out["applied"] == 0
    assert 999999 in out["missing_opportunity_ids"]
    assert json.loads(db.query(ApplicationRecord).get(ids[0]).agent_fit_json)["verdict"] == "strong"
