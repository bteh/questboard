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
            keywords_json=json.dumps(["Snowflake"]),
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


# ── LOW polish ──


def test_get_opportunity_labels_the_legacy_score_honestly(agent_db):
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    opp_id = agent_db.query(ApplicationRecord.id).first()[0]
    detail = local_agent_service.get_opportunity(agent_db, opp_id)
    # the legacy keyword-scorer artifact is named so the agent can't read it as
    # a computed resume-fit verdict, and there is no "requirements_evidence"
    assert "requirements_evidence" not in detail
    assert "legacy_keyword_score_evidence" in detail
    assert detail["retrieval"]["is_fit_assessment"] is False


def test_freshness_filter_precedes_dedup(agent_db):
    # A stale-known posting and a still-live unknown-date posting share a dedup
    # key (saved defaults keep unknown dates for agent review). Freshness must
    # run first so the live one survives instead of being evicted by the stale
    # duplicate that dedup would otherwise keep.
    from datetime import datetime, timezone
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    agent_db.add_all(
        [
            ApplicationRecord(
                job_title="Data Scientist",
                company="Same Co",
                location="Remote, US",
                vertical="career",
                date_posted="Reposted 40 Days Ago",  # stale, beyond saved window (30)
                date_found=datetime.now(timezone.utc),
            ),
            ApplicationRecord(
                job_title="Data Scientist",
                company="Same Co",
                location="Remote, US",
                vertical="career",
                date_posted="",  # unknown date -> kept for agent review
                date_found=datetime.now(timezone.utc),
            ),
        ]
    )
    agent_db.commit()

    # saved preferences (max_days_old=30), no explicit override
    result = local_agent_service.search_work(agent_db, queries=["Data Scientist"])
    titles = [r["title"] for r in result["results"]]
    assert "Data Scientist" in titles  # the live unknown-date posting survives


def test_search_payloads_flag_no_questboard_ai(agent_db):
    from app.services import local_agent_service

    work = local_agent_service.search_work(agent_db, queries=["Data Scientist"])
    quests = local_agent_service.search_side_quests(agent_db)
    assert work["questboard_funded_ai"] is False
    assert quests["questboard_funded_ai"] is False


def test_refresh_work_spends_no_questboard_ai(agent_db, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app import local_mcp
    from app.services import pipeline_service

    captured: dict = {}

    def _stub_start_run(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id="r1", status="running")

    monkeypatch.setattr(pipeline_service, "start_run", _stub_start_run)
    asyncio.run(local_mcp.refresh_work(roles=["Data Scientist"]))
    assert captured.get("use_ai") is False
    assert captured.get("durable") is True
    assert captured.get("keywords") == ["Snowflake"]


def test_strict_ranking_matches_pull_freshness_and_level_filters(agent_db):
    from app.models.workspace import WorkspacePreferences
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    prefs = agent_db.query(WorkspacePreferences).filter_by(workspace_id="local").one()
    prefs.match_strictness = "strict"
    prefs.current_level = "manager"
    now = datetime.now(timezone.utc)
    agent_db.add_all([
        ApplicationRecord(
            job_title="Senior Data Scientist",
            company="Known Date Co",
            location="Remote, US",
            is_remote=True,
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        ),
        ApplicationRecord(
            job_title="Junior Data Scientist",
            company="Junior Co",
            location="Remote, US",
            is_remote=True,
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        ),
    ])
    agent_db.commit()

    result = local_agent_service.search_work(agent_db, queries=["Data Scientist"])
    companies = {row["organization"] for row in result["results"]}

    assert "Known Date Co" in companies
    assert "Junior Co" not in companies
    assert "Local Co" not in companies  # source date is unverifiable
    assert result["filters_applied"]["match_strictness"] == "strict"
    assert result["filters_applied"]["unknown_freshness_policy"] == "exclude"


def test_refresh_is_not_advertised_idempotent():
    from app import local_mcp

    assert local_mcp.REFRESH.idempotentHint is False


def test_conflict_rejection_covers_the_domain_tokens():
    from app.services.local_agent_service import _title_is_in_lane

    # A conflict token the query doesn't share rejects even a domain overlap.
    assert not _title_is_in_lane("Data Science Manager", ["Data Manager"])
    assert not _title_is_in_lane("Program Manager, Data", ["Data Manager"])
    assert not _title_is_in_lane("Data Center Engineer", ["Data Engineer"])
    assert not _title_is_in_lane(
        "Manager, IT Infrastructure (Data Centers)",
        ["Data Infrastructure Manager"],
    )
    assert not _title_is_in_lane("Project Manager, Data", ["Data Manager"])
    # no conflict token -> keep
    assert _title_is_in_lane("Senior Data Engineer", ["Data Engineer"])


def test_balanced_ranking_does_not_cross_into_product_occupation(agent_db):
    from app.services import local_agent_service
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    agent_db.add(
        ApplicationRecord(
            job_title="Product Manager, Data Science Platform",
            company="Wrong Occupation Co",
            location="Remote, US",
            is_remote=True,
            vertical="career",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        )
    )
    agent_db.commit()

    result = local_agent_service.search_work(agent_db, queries=["Data Scientist"])
    assert "Wrong Occupation Co" not in {
        row["organization"] for row in result["results"]
    }


def test_source_age_days_parses_relative_and_unix():
    from app.services.local_agent_service import _source_age_days

    # Relative prose is only meaningful against the scrape moment (the row's
    # date_found anchor); with a fresh anchor the stated offset is the age.
    now = datetime.now(timezone.utc)
    assert _source_age_days("Posted Today", now) < 0.1
    assert 0.9 < _source_age_days("Reposted Yesterday", now) < 1.1
    assert 4.9 < _source_age_days("Reposted 5 Days Ago", now) < 5.1
    # Without an anchor, prose is unknowable, never eternally fresh.
    assert _source_age_days("Posted Today") is None
    assert _source_age_days("Reposted 5 Days Ago") is None
    # unix seconds and the same instant as 13-digit millis agree
    import time

    two_days_secs = str(int(time.time()) - 2 * 86_400)
    assert 1.5 < _source_age_days(two_days_secs) < 2.5
    assert 1.5 < _source_age_days(two_days_secs + "000") < 2.5
    assert _source_age_days("not a date") is None


def test_service_validation_raises_valueerror(agent_db):
    from app.services import local_agent_service

    with pytest.raises(ValueError):
        local_agent_service.search_side_quests(agent_db, kinds=["not-a-real-kind"])
    with pytest.raises(ValueError):
        local_agent_service.get_opportunity(agent_db, 999999)


def test_remove_command_covers_codex_and_claude():
    from scripts.install_agent_integration import remove_command

    assert remove_command("codex") == ["codex", "mcp", "remove", "questboard"]
    assert remove_command("claude")[:3] == ["claude", "mcp", "remove"]


def test_consent_endpoint_grants_and_revokes(agent_db):
    # the Settings surface (a human action) grants/revokes without the CLI
    from app.api.local_agent import get_agent_consent, set_agent_consent
    from app.schemas.resume import AgentConsentRequest

    assert get_agent_consent(agent_db).granted is False
    granted = set_agent_consent(AgentConsentRequest(grant=True), agent_db)
    assert granted.granted is True
    assert get_agent_consent(agent_db).granted is True
    set_agent_consent(AgentConsentRequest(grant=False), agent_db)
    assert get_agent_consent(agent_db).granted is False
