"""Assistant status must be instant: read the config file, never run the CLI.

Real case (Sep 9 2026): "Use these" on a role proposal took about ten
seconds, and Settings > Assistant took as long to paint. The status check
ran `claude mcp get questboard` for each assistant, and that command starts
the Questboard MCP server to test it (15 to 27 seconds on the maintainer's
Mac), leaving orphaned runtime processes behind. The panel refetched that
status after every accept.

Rules under test:
1. Status for Claude Code comes from ~/.claude.json (user scope), for Codex
   from ~/.codex/config.toml; no subprocess runs while listing clients.
2. Connected means the registered command is THIS app's runtime, the same
   rule Claude Desktop already uses; a stale entry for another binary is not
   a connection.
3. Listing every client takes well under a second.
"""

from __future__ import annotations

import json
import sys
import time
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

from app.services import agent_integration_service as svc  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setenv("CLAUDE_DESKTOP_CONFIG", str(tmp_path / "claude_desktop_config.json"))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("claude", "codex"):
        exe = fake_bin / name
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
    monkeypatch.setattr(svc, "resolve_binary", lambda client: str(fake_bin / client))

    def never(*_args, **_kwargs):
        raise AssertionError("status must not spawn a CLI")

    monkeypatch.setattr(svc.subprocess, "run", never)
    return tmp_path


def _write_claude_config(home_dir: Path, command: str | None) -> None:
    payload = {"mcpServers": {}}
    if command is not None:
        payload["mcpServers"]["questboard"] = {"type": "stdio", "command": command, "args": ["--mcp"]}
    (home_dir / ".claude.json").write_text(json.dumps(payload))


def _write_codex_config(home_dir: Path, command: str | None) -> None:
    codex_dir = home_dir / ".codex"
    codex_dir.mkdir(exist_ok=True)
    body = 'model = "gpt-5"\n'
    if command is not None:
        body += f'\n[mcp_servers.questboard]\ncommand = "{command}"\nargs = ["--data-dir", "/tmp/x"]\n'
    (codex_dir / "config.toml").write_text(body)


def test_claude_code_is_connected_when_its_user_config_names_this_runtime(home) -> None:
    _write_claude_config(home, svc.runtime_command()[0])
    status = svc.client_status("claude")
    assert status["installed"] is True
    assert status["connected"] is True


def test_claude_code_entry_for_another_binary_is_not_a_connection(home) -> None:
    _write_claude_config(home, "/somewhere/else/questboard-mcp")
    assert svc.client_status("claude")["connected"] is False


def test_claude_code_with_no_config_file_is_not_connected(home) -> None:
    assert svc.client_status("claude")["connected"] is False


def test_codex_is_connected_when_its_config_names_this_runtime(home) -> None:
    _write_codex_config(home, svc.runtime_command()[0])
    assert svc.client_status("codex")["connected"] is True


def test_codex_without_the_server_block_is_not_connected(home) -> None:
    _write_codex_config(home, None)
    assert svc.client_status("codex")["connected"] is False


def test_listing_every_client_is_instant_and_spawns_nothing(home) -> None:
    _write_claude_config(home, svc.runtime_command()[0])
    _write_codex_config(home, None)
    started = time.monotonic()
    clients = {c["id"]: c for c in svc.list_clients()}
    assert time.monotonic() - started < 1.0
    assert clients["claude"]["connected"] is True
    assert clients["codex"]["connected"] is False
    assert set(clients) == {"claude_desktop", "claude", "codex"}


def test_claude_config_dir_override_is_honoured(home, monkeypatch, tmp_path) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(other))
    (other / ".claude.json").write_text(
        json.dumps({"mcpServers": {"questboard": {"command": svc.runtime_command()[0]}}})
    )
    assert svc.client_status("claude")["connected"] is True
