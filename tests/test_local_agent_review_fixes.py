"""Review fixes for feat/local-agent-first: two HIGH regressions + the resume
consent gate. Written test-first.

1. Scientist role family: the science SQL token must retrieve "Scientist"
   titles (the alias scientist->science dropped every data/ML/research
   scientist row at the SQL prefilter).
2. Desktop --mcp env: the pipeline engine and the app/MCP engine must open the
   SAME database file, or source-health/freshness silently reads the wrong DB.
3. read_resume_for_matching must refuse resume PII until a HUMAN grants consent
   (no MCP tool can grant it), and honor revoke + expiry.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))


@pytest.fixture()
def agent_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)

    db.add(
        Workspace(
            id="local",
            name="Local",
            slug="local",
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="local",
            roles_json=json.dumps(["Data Scientist"]),
            workplace_preference="remote_friendly",
            max_days_old=30,
        )
    )
    db.add(
        WorkspaceResume(
            workspace_id="local",
            original_filename="resume.pdf",
            parse_status="parsed",
            file_sha256="a" * 64,
            extracted_text="Data engineering leader with Snowflake and Python experience.",
            updated_at=now,
        )
    )
    db.add_all(
        [
            ApplicationRecord(
                job_title="Senior Data Scientist",
                company="Local Co",
                location="Remote, US",
                vertical="career",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Research Scientist II",
                company="Lab Co",
                location="Remote, US",
                vertical="career",
                date_found=now,
            ),
        ]
    )
    db.commit()
    yield db
    generator.close()


# ── HIGH 1: scientist retrieval ──


def test_science_token_retrieves_scientist_titles(agent_db):
    from app.services.application_service import get_applications

    # "Data Scientist" normalizes to tokens {data, science}; the SQL prefilter
    # must expand "science" to the real surface forms.
    items, _total = get_applications(
        agent_db, title_token_groups=[["data", "science"]], page_size=50
    )
    titles = {i.job_title for i in items}
    assert "Senior Data Scientist" in titles


# ── HIGH 2: one database for the packaged desktop MCP path ──


def test_desktop_env_points_both_engines_at_one_database(tmp_path, monkeypatch):
    for key in ("DATA_DIR", "DATABASE_URL", "JOB_FINDER_DATABASE_URL", "JOB_FINDER_DATA_DIR"):
        monkeypatch.delenv(key, raising=False)
    from app.config import get_settings
    from app.desktop_runtime import configure_desktop_environment

    dd = tmp_path / "dd"
    configure_desktop_environment(
        data_dir=dd,
        workspace_storage_dir=tmp_path / "ws",
        resume_dir=tmp_path / "r",
        config_dir=tmp_path / "c",
    )
    expected = f"sqlite:///{dd / 'job_tracker.db'}"
    assert os.environ["DATABASE_URL"] == expected
    assert os.environ["JOB_FINDER_DATABASE_URL"] == expected
    assert os.environ["JOB_FINDER_DATA_DIR"] == str(dd)
    # both engines (app settings + job_finder pipeline) resolve the same file
    assert get_settings().resolved_database_url == expected


# ── MEDIUM: resume consent gate ──


def test_resume_refused_without_human_consent(agent_db):
    from app.services import local_agent_service

    result = local_agent_service.resume_for_matching(agent_db)
    assert result["available"] is False
    # the resume text must not leak in any field
    assert "Snowflake" not in json.dumps(result)


def test_resume_returned_only_after_human_grant(agent_db):
    from app.services import local_agent_service, resume_consent

    workspace = local_agent_service.resolve_local_workspace(agent_db)
    resume_consent.grant(workspace.id)
    result = local_agent_service.resume_for_matching(agent_db)
    assert result["available"] is True
    assert "Snowflake" in result["resume_text"]


def test_consent_honors_revoke_and_expiry(agent_db):
    from app.services import local_agent_service, resume_consent

    workspace = local_agent_service.resolve_local_workspace(agent_db)

    resume_consent.grant(workspace.id)
    resume_consent.revoke(workspace.id)
    assert local_agent_service.resume_for_matching(agent_db)["available"] is False

    resume_consent.grant(workspace.id, ttl_hours=0)  # expires immediately
    assert local_agent_service.resume_for_matching(agent_db)["available"] is False


def test_consent_file_is_the_only_grant_path(agent_db):
    # The MCP server must expose no tool that can grant consent (only a human
    # action outside the model writes it).
    from app import local_mcp

    tool_names = {name for name in dir(local_mcp) if not name.startswith("_")}
    grant_like = {n for n in tool_names if "consent" in n.lower() or "grant" in n.lower()}
    assert grant_like == set(), f"MCP module must expose no consent-grant tool: {grant_like}"
