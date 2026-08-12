"""Desktop refreshes survive assistant exit and recover without replay storms."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
for path in (str(ROOT / "backend"), str(ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)


def _run(run_id: str, *, status: str = "running") -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        run_id=run_id,
        workspace_id="workspace-1",
        status=status,
        attempt_count=0,
        max_attempts=3,
        available_at=now,
        error="",
        claimed_by="old-process",
        claimed_at=now,
        lease_expires_at=None,
        heartbeat_at=now,
        completed_at=None,
        created_at=now,
    )


def test_recovery_requeues_only_newest_run_per_workspace() -> None:
    from app.services import workspace_service

    newest = _run("newest")
    older = _run("older")
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [newest, older]

    result = workspace_service.recover_abandoned_local_search_runs(db)

    assert result == {"recovered": 1, "failed": 1}
    assert newest.status == "pending"
    assert "resumed" in newest.error
    assert older.status == "failed"
    assert "Superseded" in older.error
    assert older.completed_at is not None
    db.commit.assert_called_once()


def test_already_pending_newest_run_is_left_for_worker() -> None:
    from app.services import workspace_service

    pending = _run("pending", status="pending")
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [pending]

    result = workspace_service.recover_abandoned_local_search_runs(db)

    assert result == {"recovered": 0, "failed": 0}
    assert pending.status == "pending"
    db.commit.assert_called_once()
