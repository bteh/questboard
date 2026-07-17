from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = str(ROOT / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from install_agent_integration import add_command, remove_command


def test_codex_command_uses_a_local_stdio_process() -> None:
    command = add_command("codex", ["/tmp/questboard-mcp", "--data-dir", "/tmp/data"])
    assert command == [
        "codex",
        "mcp",
        "add",
        "questboard",
        "--",
        "/tmp/questboard-mcp",
        "--data-dir",
        "/tmp/data",
    ]
    assert "--url" not in command


def test_claude_command_is_user_scoped_and_local() -> None:
    command = add_command("claude", ["/tmp/questboard-mcp"])
    assert command[:8] == [
        "claude",
        "mcp",
        "add",
        "--transport",
        "stdio",
        "--scope",
        "user",
        "questboard",
    ]
    assert command[8:] == ["--", "/tmp/questboard-mcp"]
    assert remove_command("claude") == [
        "claude",
        "mcp",
        "remove",
        "--scope",
        "user",
        "questboard",
    ]
