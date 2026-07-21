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
