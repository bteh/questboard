"""The in-app agent connect/detect service.

Covers the pure, side-effect-free paths (detection shape, runtime command,
input validation). It never runs a real `claude`/`codex mcp add`, which would
edit the developer's actual client config.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services import agent_integration_service as svc  # noqa: E402
from app.services import agent_run_progress  # noqa: E402


def test_list_clients_shape() -> None:
    clients = svc.list_clients()
    ids = {c["id"] for c in clients}
    assert ids == {"claude", "codex"}
    for c in clients:
        assert set(c) == {"id", "name", "installed", "connected"}
        assert isinstance(c["installed"], bool)
        assert isinstance(c["connected"], bool)
        # A client that isn't installed can never read as connected.
        if not c["installed"]:
            assert c["connected"] is False


def test_runtime_command_targets_a_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    cmd = svc.runtime_command()
    assert cmd, "runtime command must not be empty"
    assert "--data-dir" in cmd
    assert str(tmp_path.resolve()) in cmd


def test_connect_and_disconnect_reject_unknown_clients() -> None:
    with pytest.raises(ValueError):
        svc.connect("gemini")
    with pytest.raises(ValueError):
        svc.disconnect("gemini")


def test_resolve_binary_returns_none_for_missing() -> None:
    assert svc.resolve_binary("questboard-not-a-real-cli-xyz") is None


def test_run_headless_rejects_unknown_client() -> None:
    with pytest.raises(ValueError):
        svc.run_headless("gemini", "do the thing")


def test_run_headless_codex_is_not_supported_yet() -> None:
    # Codex exec can't be pinned to the Questboard tools, so it declines
    # cleanly instead of spawning an unscoped run.
    out = svc.run_headless("codex", "do the thing")
    assert out["ok"] is False
    assert "Codex" in out["error"]


def test_run_headless_missing_binary_returns_error(monkeypatch) -> None:
    monkeypatch.setattr(svc, "resolve_binary", lambda client: None)
    out = svc.run_headless("claude", "do the thing")
    assert out["ok"] is False
    assert "not installed" in out["error"].lower()


def test_mcp_config_json_wires_questboard_server(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import json

    doc = json.loads(svc._mcp_config_json())
    assert svc.SERVER_NAME in doc["mcpServers"]
    server = doc["mcpServers"][svc.SERVER_NAME]
    assert server["type"] == "stdio"
    assert server["command"]


def test_parse_claude_json_success_and_error() -> None:
    good = svc._parse_claude_json(
        '{"is_error": false, "result": "top 3 fits...", "total_cost_usd": 0.5, "num_turns": 6}'
    )
    assert good["ok"] is True
    assert good["result"].startswith("top 3")
    assert good["cost_usd"] == 0.5

    bad = svc._parse_claude_json('{"is_error": true, "result": "auth failed"}')
    assert bad["ok"] is False
    assert "auth failed" in bad["error"]


def test_run_headless_parses_a_mocked_claude_run(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(svc, "get_settings_hosted", lambda: False)
    monkeypatch.setattr(svc, "resolve_binary", lambda client: "/fake/bin/claude")

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["stdin"] = kwargs.get("stdin")
        return SimpleNamespace(
            returncode=0,
            stdout='{"is_error": false, "result": "**1. Omada** ...", "total_cost_usd": 0.78, "num_turns": 6}',
            stderr="",
        )

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    out = svc.run_headless("claude", "find and rank")

    assert out["ok"] is True
    assert "Omada" in out["result"]
    assert out["num_turns"] == 6
    # Allow-list must be passed (no blanket permission bypass).
    assert "--allowedTools" in captured["command"]
    assert "--dangerously-skip-permissions" not in captured["command"]
    assert f"mcp__{svc.SERVER_NAME}__search_work" in captured["command"][captured["command"].index("--allowedTools") + 1]


def test_run_headless_refuses_in_hosted_mode(monkeypatch) -> None:
    monkeypatch.setattr(svc, "get_settings_hosted", lambda: True)
    with pytest.raises(RuntimeError):
        svc.run_headless("claude", "find and rank")


# Define Gate: find_and_rank must not silently rewrite saved preferences.

def test_run_disallowed_tools_blocks_set_career_preferences() -> None:
    assert svc.RUN_DISALLOWED_TOOLS == ("set_career_preferences",)


def test_run_allowed_tools_includes_refresh_and_status() -> None:
    assert "refresh_work" in svc.RUN_ALLOWED_TOOLS
    assert "get_refresh_status" in svc.RUN_ALLOWED_TOOLS


def test_run_allowed_tools_excludes_set_career_preferences() -> None:
    assert "set_career_preferences" not in svc.RUN_ALLOWED_TOOLS


def test_claude_command_passes_disallowed_tools() -> None:
    command = svc._run_command(
        "claude",
        "/fake/bin/claude",
        "prompt",
        "/tmp/qb-mcp-config.json",
        list(svc.RUN_ALLOWED_TOOLS),
    )
    assert "--disallowedTools" in command
    disallowed_arg = command[command.index("--disallowedTools") + 1]
    assert disallowed_arg == f"mcp__{svc.SERVER_NAME}__set_career_preferences"


def test_run_headless_mocked_claude_run_carries_disallowed_tools(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(svc, "get_settings_hosted", lambda: False)
    monkeypatch.setattr(svc, "resolve_binary", lambda client: "/fake/bin/claude")

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout='{"is_error": false, "result": "ok", "total_cost_usd": 0.1, "num_turns": 3}',
            stderr="",
        )

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    svc.run_headless("claude", "find and rank")

    command = captured["command"]
    assert "--disallowedTools" in command
    disallowed_arg = command[command.index("--disallowedTools") + 1]
    assert f"mcp__{svc.SERVER_NAME}__set_career_preferences" in disallowed_arg


# Real, currently-wired Questboard MCP tool ids (see backend/app/local_mcp.py).
_KNOWN_MCP_TOOLS = {
    "read_resume_for_matching",
    "get_career_preferences",
    "set_career_preferences",
    "propose_career_preferences",
    "search_work",
    "search_side_quests",
    "get_opportunity",
    "set_work_fit",
    "refresh_work",
    "get_refresh_status",
}


def _find_and_rank_prompt() -> str:
    from app.api.local_agent import _AGENT_TASKS

    return str(_AGENT_TASKS["find_and_rank"]["prompt"])


def test_run_allowed_tools_is_a_superset_of_tools_the_prompt_names() -> None:
    prompt = _find_and_rank_prompt()
    named = {tool for tool in _KNOWN_MCP_TOOLS if tool in prompt}
    assert named, "expected the prompt to name at least one known Questboard tool"
    assert named <= set(svc.RUN_ALLOWED_TOOLS)
    assert "set_career_preferences" not in svc.RUN_ALLOWED_TOOLS


def test_find_and_rank_prompt_does_not_instruct_saving_preferences() -> None:
    prompt = _find_and_rank_prompt()
    assert "set_career_preferences" not in prompt
    assert "save the result" not in prompt
    assert "roles you added" not in prompt
    assert "propose_career_preferences" in prompt


def test_find_and_rank_prompt_passes_roles_per_run() -> None:
    """Roles reach the tools as this run's arguments, never as saved state."""
    prompt = _find_and_rank_prompt()
    assert "refresh_work(roles=" in prompt
    assert "search_work(queries=" in prompt
    assert "this run" in prompt


def test_find_and_rank_summary_says_roles_are_proposed_not_added() -> None:
    prompt = _find_and_rank_prompt()
    assert "roles you proposed, not added" in prompt


def test_role_proposal_has_progress_label_without_preference_save_label() -> None:
    assert (
        agent_run_progress.phase_label([{"tool": "propose_career_preferences"}])
        == "Proposing role updates"
    )
    assert (
        agent_run_progress.phase_label([{"tool": "set_career_preferences"}])
        == "Working"
    )


# The pipeline shape: rank while the pull runs, never wait on it.
#
# A real run spent ~60 seconds calling get_refresh_status on a loop with
# nothing to do (the trail showed "Waiting on the sources x6"), while 1,186
# rows already on the board sat unranked. The pull runs server-side; the
# assistant's only job during it is ranking what already exists. One status
# check at the end sweeps in whatever arrived.

def test_the_prompt_does_not_instruct_a_polling_wait() -> None:
    prompt = _find_and_rank_prompt()
    assert "every 10 seconds" not in prompt
    assert "poll" not in prompt.lower()


def test_the_prompt_ranks_the_existing_board_while_the_pull_runs() -> None:
    prompt = _find_and_rank_prompt()
    assert "while" in prompt.lower() and "search_work(queries=" in prompt
    # The ranking instruction must come BEFORE the status check in reading
    # order, since the model follows the prompt's sequence.
    assert prompt.index("set_work_fit") < prompt.index("get_refresh_status(")


def test_the_prompt_checks_the_pull_exactly_once_at_the_end() -> None:
    prompt = _find_and_rank_prompt()
    assert prompt.count("get_refresh_status(") == 1
    assert "once" in prompt.lower()


def test_the_pipeline_rewrite_keeps_the_proposal_contract() -> None:
    """Speed must not quietly reopen the silent-rewrite hole."""
    prompt = _find_and_rank_prompt()
    assert "set_career_preferences" not in prompt
    assert "propose_career_preferences" in prompt
    assert "BATCHES of about 15" in prompt


# The retrieval floor: every saved role gets searched, every run.
#
# Observed 2026-07-28: a run's judged list silently dropped "Director, Data
# Engineering" and "Head of Data Platform" from the search. The user's saved
# list survived on disk (the proposal contract held), but the run still
# decided which of their roles deserved retrieval. Sharpening is for
# proposals; the search itself may only broaden.

def test_the_prompt_makes_saved_roles_the_retrieval_floor() -> None:
    prompt = _find_and_rank_prompt()
    assert "every saved role" in prompt.lower()
    assert "only add" in prompt.lower() or "never remove" in prompt.lower()


def test_the_prompt_routes_drops_through_proposals_not_the_search() -> None:
    prompt = _find_and_rank_prompt()
    assert "search it anyway" in prompt.lower()


def test_the_prompt_forbids_a_second_pull() -> None:
    """A real run called refresh_work three times: it used a fresh pull as its
    way of "checking" the first one, looping pull-shortlist-pull for five
    minutes. One pull per run; checking is get_refresh_status's job."""
    prompt = _find_and_rank_prompt()
    assert "never start a second pull" in prompt.lower()


def test_the_prompt_tells_the_sweep_to_continue_numbering() -> None:
    """The sweep restarted ranks at 1 and the board showed two #1 strong fits.
    The server guard renumbers collisions; the prompt should stop them."""
    prompt = _find_and_rank_prompt()
    assert "continue" in prompt.lower() and "highest rank" in prompt.lower()


def test_proposals_are_calibrated_to_the_users_actual_level() -> None:
    """The card proposed VP, Data Engineering and Head of AI Platform to a
    manager with a 7-report team since 2023, while dropping the IC titles the
    user restored twice. "I'm nowhere near that level." Proposals anchor on
    the resume's actual seniority, one adjacent step at most, and a role the
    user added is theirs to keep."""
    prompt = _find_and_rank_prompt()
    assert "one level" in prompt.lower()
    assert "vp" in prompt.lower() or "two levels" in prompt.lower()
    assert "do not propose dropping" in prompt.lower()
