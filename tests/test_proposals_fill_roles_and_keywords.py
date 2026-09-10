"""A click on "Suggest" must always fill roles AND keywords from the resume.

Real case (Brian, Sep 9 2026): he connected Claude Code, clicked Suggest in
Search defaults, waited 70 seconds, and nothing appeared. He had clicked
"Not now" on a suggestion four hours earlier, and a rejection quiets every
proposal for a week. That rule exists for unprompted suggestions during a
refresh; a run the person started is the opposite of unprompted. And a
proposal only ever carried roles, so keywords stayed at whatever the upload
guessed.

Rules under test:
1. A user-requested run records a proposal even inside the quiet week. An
   unprompted run still waits it out.
2. A proposal carries keywords. Accepting patches roles and merges the
   proposed keywords into the saved ones (case-insensitive, capped).
3. The app marks the task as user-requested when it launches the run, and
   the MCP tool passes that flag through to the service.
4. An existing desktop database gains the new column on startup.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

SAVED_ROLES = ["Data Engineering Manager"]
SAVED_KEYWORDS = ["data platform", "Snowflake"]


@pytest.fixture()
def proposal_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    db.add(
        Workspace(
            id="configured",
            name="Configured",
            slug="configured",
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="configured",
            roles_json=json.dumps(SAVED_ROLES),
            keywords_json=json.dumps(SAVED_KEYWORDS),
            workplace_preference="remote_friendly",
            max_days_old=14,
            current_level="manager",
        )
    )
    db.commit()
    yield db
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


def _reject_a_suggestion(db) -> None:
    from app.services import local_agent_service as svc

    first = svc.propose_career_preferences(db, roles=["Head of Data Platform"], rationale="wider net")
    svc.decide_role_proposal(db, first["id"], accept=False)


# ── 1. a click beats the quiet week ─────────────────────────────────────────

def test_user_requested_run_proposes_inside_the_quiet_week(proposal_db) -> None:
    from app.services import local_agent_service as svc

    _reject_a_suggestion(proposal_db)

    asked = svc.propose_career_preferences(
        proposal_db,
        roles=["Data Engineering Manager", "Data Platform Manager"],
        rationale="you asked",
        requested_by_user=True,
    )
    assert asked["status"] == "pending"
    pending = svc.list_role_proposals(proposal_db, status="pending")["proposals"]
    assert [p["id"] for p in pending] == [asked["id"]]


def test_unprompted_run_still_waits_out_the_quiet_week(proposal_db) -> None:
    from app.services import local_agent_service as svc

    _reject_a_suggestion(proposal_db)

    quiet = svc.propose_career_preferences(
        proposal_db,
        roles=["Data Engineering Manager", "Data Platform Manager"],
        rationale="unprompted",
    )
    assert quiet["status"] == "rejected"
    assert svc.list_role_proposals(proposal_db, status="pending")["proposals"] == []


# ── 2. keywords ride along and merge on accept ──────────────────────────────

def test_proposal_carries_keywords_and_accept_merges_them(proposal_db) -> None:
    from app.models.workspace import WorkspacePreferences
    from app.services import local_agent_service as svc

    proposed = svc.propose_career_preferences(
        proposal_db,
        roles=["Data Engineering Manager", "Data Platform Manager"],
        rationale="two titles, three skills",
        keywords=["Airflow", "snowflake", "dbt"],
    )
    assert proposed["proposed_keywords"] == ["Airflow", "snowflake", "dbt"]
    listed = svc.list_role_proposals(proposal_db, status="pending")["proposals"][0]
    assert listed["proposed_keywords"] == ["Airflow", "snowflake", "dbt"]

    decision = svc.decide_role_proposal(proposal_db, proposed["id"], accept=True)
    assert decision["roles"] == ["Data Engineering Manager", "Data Platform Manager"]
    # Saved keywords keep their order; new ones append; "snowflake" already
    # exists as "Snowflake" and is not added twice.
    assert decision["keywords"] == ["data platform", "Snowflake", "Airflow", "dbt"]

    prefs = proposal_db.query(WorkspacePreferences).one()
    assert json.loads(prefs.roles_json) == ["Data Engineering Manager", "Data Platform Manager"]
    assert json.loads(prefs.keywords_json) == ["data platform", "Snowflake", "Airflow", "dbt"]


def test_accept_without_keywords_leaves_saved_keywords_alone(proposal_db) -> None:
    from app.models.workspace import WorkspacePreferences
    from app.services import local_agent_service as svc

    proposed = svc.propose_career_preferences(proposal_db, roles=["Data Platform Manager"], rationale="one")
    decision = svc.decide_role_proposal(proposal_db, proposed["id"], accept=True)
    assert decision["keywords"] == SAVED_KEYWORDS
    prefs = proposal_db.query(WorkspacePreferences).one()
    assert json.loads(prefs.keywords_json) == SAVED_KEYWORDS


def test_keyword_merge_is_capped(proposal_db) -> None:
    from app.services import local_agent_service as svc

    many = [f"skill{i}" for i in range(30)]
    proposed = svc.propose_career_preferences(
        proposal_db, roles=["Data Platform Manager"], rationale="many", keywords=many
    )
    decision = svc.decide_role_proposal(proposal_db, proposed["id"], accept=True)
    assert len(decision["keywords"]) == svc.KEYWORDS_CAP
    assert decision["keywords"][:2] == SAVED_KEYWORDS


# ── 3. the app says "the person asked", the tool passes it on ───────────────

def test_progress_marks_the_task_the_person_asked_for(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.services import agent_run_progress

    agent_run_progress.clear()
    assert agent_run_progress.requested_task() == ""

    agent_run_progress.mark_requested("propose_roles")
    assert agent_run_progress.requested_task() == "propose_roles"
    # The mark survives the steps the run records after it.
    agent_run_progress.record("read_resume_for_matching")
    assert agent_run_progress.requested_task() == "propose_roles"
    # A stale mark (an old click) no longer counts.
    assert agent_run_progress.requested_task(max_age_seconds=0) == ""
    # The next run starts clean.
    agent_run_progress.clear()
    assert agent_run_progress.requested_task() == ""


def test_mcp_tool_passes_the_request_flag_and_keywords_to_the_service(
    proposal_db, monkeypatch
) -> None:
    from app import local_mcp
    from app.services import agent_run_progress, local_agent_service

    seen: list[dict] = []

    def recorder(db, roles, rationale="", keywords=None, *, requested_by_user=False, **_):
        seen.append({"roles": roles, "keywords": keywords, "requested_by_user": requested_by_user})
        return {"id": 1, "status": "pending", "proposed_roles": roles, "proposed_keywords": keywords or []}

    monkeypatch.setattr(local_agent_service, "propose_career_preferences", recorder)

    agent_run_progress.clear()
    agent_run_progress.mark_requested("propose_roles")
    local_mcp.propose_career_preferences(roles=["Data Platform Manager"], rationale="r", keywords=["dbt"])
    assert seen[-1] == {"roles": ["Data Platform Manager"], "keywords": ["dbt"], "requested_by_user": True}

    agent_run_progress.clear()
    local_mcp.propose_career_preferences(roles=["Data Platform Manager"], rationale="r")
    assert seen[-1]["requested_by_user"] is False


def test_run_endpoint_marks_a_propose_roles_run_as_requested(proposal_db, monkeypatch) -> None:
    from app.api import local_agent
    from app.schemas.resume import AgentRunRequest
    from app.services import agent_integration_service, agent_run_progress, resume_consent

    monkeypatch.setattr(resume_consent, "is_granted", lambda _workspace_id: True)
    marks: list[str] = []

    def fake_run(client, prompt):
        marks.append(agent_run_progress.requested_task())
        return {"ok": True, "result": "Proposed.", "error": "", "cost_usd": None, "num_turns": 3}

    monkeypatch.setattr(agent_integration_service, "run_headless", fake_run)
    monkeypatch.setattr(local_agent, "_require_local", lambda: None)

    local_agent.run_agent(AgentRunRequest(task="propose_roles", client="claude"), db=proposal_db)
    assert marks == ["propose_roles"], "the run must see the mark while it executes"


def test_intent_endpoint_marks_a_pasted_prompt_run_as_requested(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.api import local_agent
    from app.schemas.resume import AgentIntentRequest
    from app.services import agent_run_progress

    monkeypatch.setattr(local_agent, "_require_local", lambda: None)
    local_agent.mark_agent_intent(AgentIntentRequest(task="propose_roles"))
    assert agent_run_progress.requested_task() == "propose_roles"


# ── 4. prompts and schema ───────────────────────────────────────────────────

def test_propose_roles_prompt_asks_for_keywords_too() -> None:
    from app.api.local_agent import _AGENT_TASKS

    prompt = str(_AGENT_TASKS["propose_roles"]["prompt"]).lower()
    assert "keywords" in prompt
    assert "set_career_preferences" in prompt, "still forbids saving directly"


def test_existing_database_gains_the_keywords_column(tmp_path, monkeypatch) -> None:
    from sqlalchemy import create_engine, inspect, text

    data_dir = tmp_path / "legacy-data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    legacy = create_engine(database_url)
    with legacy.begin() as conn:
        conn.execute(text("CREATE TABLE workspaces (id VARCHAR(64) PRIMARY KEY, last_active_at DATETIME)"))
        conn.execute(
            text(
                "CREATE TABLE agent_role_proposals ("
                "id INTEGER PRIMARY KEY, workspace_id VARCHAR(64), base_roles_json TEXT, "
                "proposed_roles_json TEXT, rationale VARCHAR(500), status VARCHAR(16), "
                "created_at DATETIME, decided_at DATETIME)"
            )
        )
    legacy.dispose()

    from app.models.database import init_db

    init_db(str(db_path))

    check = create_engine(database_url)
    try:
        columns = {c["name"] for c in inspect(check).get_columns("agent_role_proposals")}
        assert "proposed_keywords_json" in columns
    finally:
        check.dispose()
