"""An assistant run that ends before its pull must hand the pull to the board.

Real case (Brian's board, Nov 11 2026): find_and_rank started a pull at
17:49:07, ranked the existing board, checked the pull once at 17:49:23 and
returned. The pull finished at 17:51:10. The board toasted "Board updated"
two minutes before the new jobs landed, so he ran another pull to be sure.

The prompt ranks while the pull runs on purpose (speed). The fix is the
handoff: /api/agent/run returns the still-active pull's run id so the board
can follow it to completion and say when it actually landed.
"""

from __future__ import annotations

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


@pytest.fixture()
def run_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.api import local_agent
    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspaceSearchRun
    from app.schemas.resume import AgentRunRequest
    from app.services import agent_integration_service, local_agent_service, resume_consent

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)
    workspace = Workspace(
        id="ws",
        name="Local",
        slug="ws",
        last_active_at=now,
        expires_at=now + timedelta(days=7),
    )
    db.add(workspace)
    db.commit()

    monkeypatch.setattr(local_agent, "_require_local", lambda: None)
    monkeypatch.setattr(local_agent_service, "resolve_local_workspace", lambda *_a, **_k: workspace)
    monkeypatch.setattr(resume_consent, "is_granted", lambda *_a, **_k: True)

    def start_pull(status: str):
        def fake_headless(_client, _prompt, *args, **kwargs):
            db.add(WorkspaceSearchRun(workspace_id="ws", run_id="pull1", status=status, mode="search_only"))
            db.commit()
            return {"ok": True, "result": "ranked", "error": "", "cost_usd": None, "num_turns": 3}

        monkeypatch.setattr(agent_integration_service, "run_headless", fake_headless)

    def run():
        return local_agent.run_agent(AgentRunRequest(task="find_and_rank", client="claude"), db=db)

    try:
        yield SimpleNamespace(start_pull=start_pull, run=run)
    finally:
        generator.close()


def test_a_run_that_returns_mid_pull_hands_back_the_pull(run_env) -> None:
    run_env.start_pull("running")
    out = run_env.run()
    assert out.ok
    assert out.pull_run_id == "pull1"


def test_a_run_whose_pull_already_landed_hands_back_nothing(run_env) -> None:
    run_env.start_pull("completed")
    out = run_env.run()
    assert out.ok
    assert out.pull_run_id is None
