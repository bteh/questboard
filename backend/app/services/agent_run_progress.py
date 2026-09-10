"""Where the connected assistant's run has actually got to.

The assistant runs as a separate process with no SSE feed, so the board had
nothing real to report and showed a stopwatch dressed as progress: past 100
seconds it read "Ranking against your experience" whether or not the run had
started ranking. On one run it claimed ranking at 2:36 while `set_work_fit`
had not been called at all.

Every step the run takes IS an MCP tool call, and those all pass through one
wrapper in `local_mcp`. Stamping them there gives five true checkpoints.

This is ephemeral run state, so it lives in a file beside the database rather
than in the board's tables: it is worthless after the run, worth no migration,
and the MCP server is a separate process that already shares the data dir.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FILENAME = "agent_run_progress.json"

# The run's shape, in the order it happens. A tool not listed here still
# records; it just doesn't rename the phase.
_PHASES: dict[str, str] = {
    "read_resume_for_matching": "Reading your resume",
    "get_career_preferences": "Reading your saved search",
    "propose_career_preferences": "Proposing role updates",
    "refresh_work": "Pulling fresh postings",
    # A single end-of-run check now, not a polling loop; the label has to
    # read sensibly after ranking, not just during a wait.
    "get_refresh_status": "Checking the source pull",
    "search_work": "Reading the shortlist",
    "set_work_fit": "Writing your rankings",
}


def _progress_path() -> Path:
    return Path(os.environ.get("DATA_DIR", ".")) / _FILENAME


def _write(payload: dict[str, Any]) -> None:
    path = _progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _load() -> dict[str, Any]:
    try:
        payload = json.loads(_progress_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read() -> dict[str, Any]:
    """The current run's steps, oldest first. Empty when nothing is running."""
    steps = _load().get("steps")
    return {"steps": steps} if isinstance(steps, list) else {"steps": []}


def work_fit_run_id() -> str:
    """The id this run's rankings are being written under, or "" if none yet.

    Rankings land in batches so a run that outlives its timeout keeps the
    verdicts it already decided. Every batch after the first has to join the
    same run instead of clearing the board, and this is how a batch knows it
    is not the first. Unreadable state answers "" so the fallback is the old
    single-write behavior, never two runs blended on one board.
    """
    value = _load().get("work_fit_run_id")
    return str(value) if isinstance(value, str) else ""


def set_work_fit_run_id(run_id: str) -> None:
    """Claim the run id for this run's first batch of rankings."""
    try:
        payload = _load()
        payload["work_fit_run_id"] = run_id
        payload.setdefault("steps", [])
        _write(payload)
    except Exception:  # noqa: BLE001 - never break the write it accompanies
        logger.debug("could not stamp work fit run id", exc_info=True)


def mark_requested(task: str) -> None:
    """Note that the person asked for ``task`` themselves.

    A proposal the person asked for must always get an answer; the quiet
    week after a "Not now" is for unprompted suggestions during a refresh.
    The MCP server is a separate process, so the mark rides in this file
    alongside the steps. Never raises.
    """
    try:
        payload = _load()
        payload["requested_task"] = str(task)
        payload["requested_at"] = datetime.now(timezone.utc).isoformat()
        payload.setdefault("steps", [])
        _write(payload)
    except Exception:  # noqa: BLE001 - a lost mark must not fail the run
        logger.debug("could not mark requested task %s", task, exc_info=True)


def requested_task(max_age_seconds: int = 1800) -> str:
    """The task the person asked for, or "" when none or the mark is stale."""
    payload = _load()
    task = payload.get("requested_task")
    stamped = payload.get("requested_at")
    if not isinstance(task, str) or not isinstance(stamped, str):
        return ""
    try:
        marked_at = datetime.fromisoformat(stamped)
    except ValueError:
        return ""
    if marked_at.tzinfo is None:
        marked_at = marked_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - marked_at).total_seconds()
    return task if age < max_age_seconds else ""


def clear() -> None:
    """Start a fresh run. Called when the app launches the assistant."""
    try:
        _write({"steps": []})
    except OSError:
        logger.debug("could not clear agent progress", exc_info=True)


def erase() -> None:
    """Remove all persisted assistant progress during a privacy reset."""
    try:
        _progress_path().unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not erase agent progress", exc_info=True)


def record(tool: str) -> None:
    """Note that the run reached ``tool``.

    Never raises. This is a nicety on top of the assistant's real work, and a
    read-only disk must not turn a working run into a failed one.

    A repeat of the tool just recorded bumps its count instead of appending:
    the run polls ``get_refresh_status`` every ten seconds, and six identical
    rows say less than one row that knows it is still waiting.
    """
    try:
        # Merge into whatever is already there. Rewriting only the steps would
        # drop the run id the ranking batches key off, and the second batch
        # would then read as a first one and clear the first batch's work.
        payload = _load()
        steps = payload.get("steps")
        if not isinstance(steps, list):
            steps = []
        now = datetime.now(timezone.utc).isoformat()
        if steps and steps[-1].get("tool") == tool:
            steps[-1]["count"] = int(steps[-1].get("count", 1)) + 1
            steps[-1]["at"] = now
        else:
            steps.append({"tool": tool, "at": now, "count": 1})
        payload["steps"] = steps
        _write(payload)
    except Exception:  # noqa: BLE001 - progress must never break a tool call
        logger.debug("could not record agent progress for %s", tool, exc_info=True)


def phase_label(steps: list[dict[str, Any]]) -> str:
    """Plain words for where the run is, from the last step it actually took."""
    if not steps:
        return "Starting up"
    return _PHASES.get(str(steps[-1].get("tool") or ""), "Working")
