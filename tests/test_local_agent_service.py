from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    assert payload["server_funded_ai"] is False
    assert payload["results"][0]["retrieval"]["is_fit_assessment"] is False


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
    assert health["server_funded_ai"] is False


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
        "refresh_work",
        "get_source_status",
        "set_opportunity_status",
    }.issubset(names)
