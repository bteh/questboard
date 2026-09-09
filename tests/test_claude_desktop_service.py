"""Claude Desktop connects through its config file, not a CLI.

Pinned Sep 8 2026 for a first user who has only ever used Claude in a
window: no Terminal, no Claude Code. The connector must add exactly one
entry, leave the person's other servers alone, and come out cleanly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

from app.services import claude_desktop_service as svc

RUNTIME = ["/Applications/Questboard.app/Contents/Resources/sidecars/questboard-runtime", "--mcp", "--data-dir", "/x"]


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "claude_desktop_config.json"
    monkeypatch.setenv("CLAUDE_DESKTOP_CONFIG", str(path))
    monkeypatch.setattr(svc, "_APP_BUNDLES", (tmp_path / "Claude.app",))
    (tmp_path / "Claude.app").mkdir()
    monkeypatch.setattr(svc, "_changed_this_session", False)
    return path


def test_connect_adds_only_the_questboard_entry_and_keeps_other_servers(config):
    config.write_text(json.dumps({"mcpServers": {"filesystem": {"command": "npx", "args": ["fs"]}}, "theme": "dark"}))
    result = svc.connect(RUNTIME)
    written = json.loads(config.read_text())
    assert written["mcpServers"]["filesystem"] == {"command": "npx", "args": ["fs"]}
    assert written["mcpServers"]["questboard"] == {"command": RUNTIME[0], "args": RUNTIME[1:]}
    assert written["theme"] == "dark"
    assert result["connected"] is True
    assert result["restart_required"] is True
    assert config.with_suffix(".json.bak").exists()


def test_connect_creates_the_file_when_claude_has_none_yet(config):
    assert not config.exists()
    svc.connect(RUNTIME)
    assert json.loads(config.read_text())["mcpServers"]["questboard"]["command"] == RUNTIME[0]


def test_disconnect_removes_only_ours(config):
    config.write_text(json.dumps({"mcpServers": {"questboard": {"command": RUNTIME[0]}, "other": {"command": "x"}}}))
    result = svc.disconnect(RUNTIME)
    assert json.loads(config.read_text())["mcpServers"] == {"other": {"command": "x"}}
    assert result["connected"] is False


def test_status_reports_not_installed_without_the_app(config, monkeypatch):
    monkeypatch.setattr(svc, "_APP_BUNDLES", (config.parent / "missing.app",))
    assert svc.status(RUNTIME)["installed"] is False
    with pytest.raises(ValueError) as excinfo:
        svc.connect(RUNTIME)
    assert "claude.ai/download" in str(excinfo.value)


def test_a_stale_entry_for_another_runtime_does_not_count_as_connected(config):
    config.write_text(json.dumps({"mcpServers": {"questboard": {"command": "/old/path/questboard-mcp"}}}))
    assert svc.is_connected(RUNTIME) is False
