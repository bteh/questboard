"""Stage 2a: role proposals record intent without ever touching saved prefs.

propose_career_preferences writes a pending row that captures the roles the
assistant would suggest and the roles currently saved (its "base"). Accepting
re-reads current preferences and refuses if they drifted since the proposal
was made (the base went stale); it never blends stale data into a save.
Rejecting never touches workspace_preferences at all.
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


@pytest.fixture()
def role_proposal_db(tmp_path, monkeypatch):
    # A temp DB per test, never the desktop runtime's symlinked default path.
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
            roles_json=json.dumps(["Data Engineering Manager"]),
            keywords_json=json.dumps(["data platform", "Snowflake"]),
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


def test_local_startup_creates_proposal_table_for_an_existing_database(
    tmp_path, monkeypatch
) -> None:
    from sqlalchemy import create_engine, inspect, text

    data_dir = tmp_path / "legacy-data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    legacy_engine = create_engine(database_url)
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE workspaces ("
                "id VARCHAR(64) PRIMARY KEY, "
                "last_active_at DATETIME"
                ")"
            )
        )
    legacy_engine.dispose()

    from app.models.database import init_db

    init_db(str(db_path))

    verification_engine = create_engine(database_url)
    try:
        assert "agent_role_proposals" in inspect(verification_engine).get_table_names()
    finally:
        verification_engine.dispose()


def test_proposing_supersedes_prior_pending(role_proposal_db) -> None:
    from app.services import local_agent_service as svc

    first = svc.propose_career_preferences(
        role_proposal_db,
        roles=["Head of Data Platform"],
        rationale="Broader scope, same skills.",
    )
    assert first["status"] == "pending"

    second = svc.propose_career_preferences(
        role_proposal_db,
        roles=["AI Platform Lead"],
        rationale="Better match for the resume.",
    )
    assert second["status"] == "pending"
    assert second["id"] != first["id"]

    pending = svc.list_role_proposals(role_proposal_db, status="pending")["proposals"]
    assert [p["id"] for p in pending] == [second["id"]]

    superseded = svc.list_role_proposals(role_proposal_db, status="superseded")["proposals"]
    assert [p["id"] for p in superseded] == [first["id"]]
    assert superseded[0]["decided_at"] is not None


def test_propose_captures_current_saved_roles_as_base(role_proposal_db) -> None:
    from app.services import local_agent_service as svc

    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    assert proposal["base_roles"] == ["Data Engineering Manager"]
    assert proposal["proposed_roles"] == ["Head of Data Platform"]
    assert proposal["rationale"] == "wider net"

    # Never touches saved preferences.
    prefs = svc.career_preferences(role_proposal_db)["preferences"]
    assert prefs["roles"] == ["Data Engineering Manager"]


def test_accept_patches_roles_only_and_leaves_other_fields_untouched(role_proposal_db) -> None:
    from app.services import local_agent_service as svc
    from app.models.workspace import WorkspacePreferences

    before = role_proposal_db.query(WorkspacePreferences).one()
    unchanged_before = {
        column.name: getattr(before, column.name)
        for column in WorkspacePreferences.__table__.columns
        if column.name not in {"roles_json", "updated_at"}
    }

    proposal = svc.propose_career_preferences(
        role_proposal_db,
        roles=["Head of Data Platform", "AI Platform Lead"],
        rationale="wider net",
    )
    result = svc.decide_role_proposal(role_proposal_db, proposal["id"], accept=True)
    assert result["status"] == "accepted"
    assert result["external_action_performed"] is False

    prefs = svc.career_preferences(role_proposal_db)["preferences"]
    assert prefs["roles"] == ["Head of Data Platform", "AI Platform Lead"]
    # Every other saved field survives untouched.
    assert prefs["keywords"] == ["data platform", "Snowflake"]
    assert prefs["workplace_preference"] == "remote_friendly"
    assert prefs["max_days_old"] == 14
    assert prefs["current_level"] == "manager"

    after = role_proposal_db.query(WorkspacePreferences).one()
    unchanged_after = {
        column.name: getattr(after, column.name)
        for column in WorkspacePreferences.__table__.columns
        if column.name not in {"roles_json", "updated_at"}
    }
    assert unchanged_after == unchanged_before

    still_pending = svc.list_role_proposals(role_proposal_db, status="pending")["proposals"]
    assert still_pending == []


def test_accept_on_stale_base_returns_conflict_without_writing(role_proposal_db) -> None:
    from app.services import local_agent_service as svc

    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )

    # The person (or another proposal) changes saved roles after the proposal
    # was made; the base the proposal captured is now stale.
    svc.set_career_preferences(role_proposal_db, roles=["Director of Data"])

    with pytest.raises(svc.RoleProposalConflict):
        svc.decide_role_proposal(role_proposal_db, proposal["id"], accept=True)

    # Nothing about the stale proposal's decide attempt touched preferences.
    prefs = svc.career_preferences(role_proposal_db)["preferences"]
    assert prefs["roles"] == ["Director of Data"]

    # The proposal itself is untouched: still pending, not silently decided.
    still_pending = svc.list_role_proposals(role_proposal_db, status="pending")["proposals"]
    assert [p["id"] for p in still_pending] == [proposal["id"]]


def test_accept_is_atomic_when_the_preference_save_fails(
    role_proposal_db, monkeypatch
) -> None:
    """Accept claims the proposal row first, then saves preferences, in one
    transaction. If the save blows up after the claim, the rollback must
    unwind the claim too: a proposal marked accepted whose roles never landed
    would lie about what the board is searching."""
    from app.models.workspace import AgentRoleProposal
    from app.services import local_agent_service as svc

    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("simulated preference save failure")

    monkeypatch.setattr(
        svc.workspace_service, "save_workspace_preferences", fail_save
    )
    with pytest.raises(RuntimeError, match="simulated preference save failure"):
        svc.decide_role_proposal(role_proposal_db, proposal["id"], accept=True)
    role_proposal_db.rollback()

    role_proposal_db.expire_all()
    prefs = svc.career_preferences(role_proposal_db)["preferences"]
    assert prefs["roles"] == ["Data Engineering Manager"]
    stored_proposal = role_proposal_db.get(AgentRoleProposal, proposal["id"])
    assert stored_proposal.status == "pending", "the claim must roll back too"
    assert stored_proposal.decided_at is None


def test_reject_writes_nothing_to_preferences(role_proposal_db) -> None:
    from app.models.workspace import WorkspacePreferences
    from app.services import local_agent_service as svc

    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    before = {
        column.name: getattr(role_proposal_db.query(WorkspacePreferences).one(), column.name)
        for column in WorkspacePreferences.__table__.columns
    }
    result = svc.decide_role_proposal(role_proposal_db, proposal["id"], accept=False)
    assert result["status"] == "rejected"
    assert result["decided_at"] is not None

    after = {
        column.name: getattr(role_proposal_db.query(WorkspacePreferences).one(), column.name)
        for column in WorkspacePreferences.__table__.columns
    }
    assert after == before

    prefs = svc.career_preferences(role_proposal_db)["preferences"]
    assert prefs["roles"] == ["Data Engineering Manager"]

    pending = svc.list_role_proposals(role_proposal_db, status="pending")["proposals"]
    assert pending == []


def test_mcp_server_declares_the_tool_with_write_annotations() -> None:
    import asyncio

    from app.local_mcp import mcp

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert "propose_career_preferences" in tools
    annotations = tools["propose_career_preferences"].annotations
    assert annotations.readOnlyHint is False
    assert annotations.destructiveHint is False


def test_full_agent_run_trail_shows_proposing_role_updates_phase(role_proposal_db) -> None:
    from app.local_mcp import propose_career_preferences as mcp_propose
    from app.services import agent_run_progress

    agent_run_progress.clear()
    mcp_propose(roles=["Head of Data Platform"], rationale="wider net")

    steps = agent_run_progress.read()["steps"]
    assert steps[-1]["tool"] == "propose_career_preferences"
    assert agent_run_progress.phase_label(steps) == "Proposing role updates"


def test_headless_agent_run_can_call_propose_career_preferences() -> None:
    from app.services import agent_integration_service

    assert "propose_career_preferences" in agent_integration_service.RUN_ALLOWED_TOOLS


def test_accept_refuses_a_proposal_superseded_after_it_was_read(
    role_proposal_db,
) -> None:
    """The lost-update race: a run proposes again while the user's accept is
    mid-flight. decide read the proposal as pending, the run marks it
    superseded, and an unguarded accept would clobber that with 'accepted'
    and save roles a newer proposal already replaced.

    The stale read is reproduced through the identity map: the decide call
    holds a 'pending' object while the database row already says superseded,
    which is exactly the state the race window creates.
    """
    from sqlalchemy import text

    from app.models.workspace import AgentRoleProposal
    from app.services import local_agent_service as svc

    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    # Load the ORM object so decide's db.get() sees a cached 'pending' row.
    stale = role_proposal_db.get(AgentRoleProposal, proposal["id"])
    assert stale.status == "pending"

    # A concurrent run supersedes it on its own connection and commits, the
    # way a real second session would. Issuing it through this session would
    # share the accept's transaction and get unwound by the conflict rollback,
    # which is not how the race behaves.
    with role_proposal_db.get_bind().engine.connect() as other:
        other.execute(
            text("UPDATE agent_role_proposals SET status = 'superseded' WHERE id = :i"),
            {"i": proposal["id"]},
        )
        other.commit()

    with pytest.raises(svc.RoleProposalConflict):
        svc.decide_role_proposal(role_proposal_db, proposal["id"], accept=True)

    role_proposal_db.rollback()
    role_proposal_db.expire_all()
    prefs = svc.career_preferences(role_proposal_db)["preferences"]
    assert prefs["roles"] == ["Data Engineering Manager"], "roles must not change"
    stored = role_proposal_db.get(AgentRoleProposal, proposal["id"])
    assert stored.status == "superseded", "the newer run's verdict must survive"


def test_a_long_rationale_is_trimmed_at_a_word_not_mid_letter(role_proposal_db) -> None:
    """The board showed a proposal ending "as a common phrasi": the rationale
    was hard-cut at 500 characters mid-word and stored that way. A trim the
    reader can see must end at a word with an ellipsis."""
    from app.services import local_agent_service as svc

    long_rationale = ("alignment with your platform background " * 20).strip()
    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale=long_rationale
    )
    stored = proposal["rationale"]
    assert len(stored) <= 500
    assert stored.endswith("…")
    # The character before the ellipsis ends a whole word from the source.
    last_word = stored[:-1].rstrip().split()[-1]
    assert last_word in long_rationale.split()


def test_a_short_rationale_is_stored_untouched(role_proposal_db) -> None:
    from app.services import local_agent_service as svc

    proposal = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    assert proposal["rationale"] == "wider net"


def test_reproposing_the_same_pending_list_does_not_spam(role_proposal_db) -> None:
    """Every run proposed again, superseding and recreating an identical
    proposal, so the card nagged on every pull. Proposing the list that is
    already pending returns the pending proposal instead of a churned copy."""
    from app.services import local_agent_service as svc

    first = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    second = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="same idea again"
    )
    assert second["id"] == first["id"]
    assert second["status"] == "pending"


def test_a_recently_rejected_list_is_not_reproposed(role_proposal_db) -> None:
    """"Keep mine" means no. The same list coming back the next run turns the
    card into a nag the user already answered."""
    from app.services import local_agent_service as svc

    first = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    svc.decide_role_proposal(role_proposal_db, first["id"], accept=False)

    again = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="try again"
    )
    assert again["status"] == "rejected", "the earlier answer stands"
    pending = svc.list_role_proposals(role_proposal_db, status="pending")
    assert pending["proposals"] == []


def test_a_genuinely_new_list_still_proposes_after_a_rejection(role_proposal_db) -> None:
    from app.services import local_agent_service as svc

    first = svc.propose_career_preferences(
        role_proposal_db, roles=["Head of Data Platform"], rationale="wider net"
    )
    svc.decide_role_proposal(role_proposal_db, first["id"], accept=False)

    fresh = svc.propose_career_preferences(
        role_proposal_db, roles=["VP, Data Engineering"], rationale="different idea"
    )
    assert fresh["status"] == "pending"
    assert fresh["id"] != first["id"]
