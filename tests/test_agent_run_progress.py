"""The assistant run must report where it actually is, not where a clock guesses.

Real report, 2026-07-27: the board read "Ranking against your experience · 2:36"
while the run had not called set_work_fit at all. The label was a stopwatch:

    const phase = elapsed < 8 ? PHASES[0] : elapsed < 100 ? PHASES[1] : PHASES[2]

Past 100 seconds it claimed ranking regardless of what the run was doing. The
assistant is a separate process with no SSE feed, so the UI had nothing real to
show and invented something instead.

Every step the run takes is an MCP tool call, and those all funnel through one
wrapper in local_mcp. Stamping them gives the UI five true checkpoints. This is
ephemeral run state, so it lives in a file beside the DB rather than in the
board's tables: nothing here is worth a migration or surviving a restart.
"""

from __future__ import annotations

import json
import sys
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
def progress(tmp_path, monkeypatch):
    """Resolve the module at test time; other tests re-import app.* under their
    own temp dirs and a module-level import would bind a stale object."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.services import agent_run_progress as module

    monkeypatch.setattr(module, "_progress_path", lambda: tmp_path / "agent_progress.json")
    module.clear()
    return module


def test_a_recorded_step_shows_up_in_order(progress):
    progress.record("read_resume_for_matching")
    progress.record("set_career_preferences")

    steps = progress.read()["steps"]
    assert [s["tool"] for s in steps] == [
        "read_resume_for_matching",
        "set_career_preferences",
    ]


def test_every_step_carries_when_it_happened(progress):
    progress.record("refresh_work")
    step = progress.read()["steps"][0]
    assert step["at"], "a step with no time cannot drive a clock"


def test_polling_the_status_of_a_run_that_has_not_started_is_empty(progress):
    assert progress.read() == {"steps": []}


def test_clearing_drops_the_previous_run(progress):
    progress.record("search_work")
    progress.clear()
    assert progress.read()["steps"] == []


def test_repeated_polling_of_one_tool_collapses(progress):
    """The run polls get_refresh_status every ~10s. Seeing it six times is
    noise; that it is still waiting is the signal."""
    progress.record("refresh_work")
    for _ in range(6):
        progress.record("get_refresh_status")

    steps = progress.read()["steps"]
    assert [s["tool"] for s in steps] == ["refresh_work", "get_refresh_status"]
    assert steps[-1]["count"] == 6


def test_a_corrupt_file_reads_as_empty_rather_than_exploding(progress, tmp_path):
    (tmp_path / "agent_progress.json").write_text("{not json")
    assert progress.read() == {"steps": []}


def test_recording_never_raises_into_the_tool_call(progress, monkeypatch):
    """Progress is a nicety. A failure to write it must never break the
    assistant's actual work."""
    def boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(progress, "_write", boom)
    progress.record("search_work")  # must not raise


def test_the_file_is_valid_json_on_disk(progress, tmp_path):
    progress.record("set_work_fit")
    payload = json.loads((tmp_path / "agent_progress.json").read_text())
    assert payload["steps"][0]["tool"] == "set_work_fit"


# ── the label the board shows ───────────────────────────────────────────────

def test_the_phase_names_the_last_real_step(progress):
    from app.services.agent_run_progress import phase_label

    assert phase_label([]) == "Starting up"
    assert phase_label([{"tool": "read_resume_for_matching"}]) == "Reading your resume"
    assert phase_label([{"tool": "refresh_work"}]) == "Pulling fresh postings"
    assert phase_label([{"tool": "search_work"}]) == "Reading the shortlist"
    assert phase_label([{"tool": "set_work_fit"}]) == "Writing your rankings"


def test_an_unknown_tool_does_not_blank_the_label(progress):
    from app.services.agent_run_progress import phase_label

    assert phase_label([{"tool": "server_info"}]) == "Working"
