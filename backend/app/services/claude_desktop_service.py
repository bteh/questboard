"""Connect the Claude desktop app to Questboard's local MCP server.

Claude Desktop has no CLI to register servers with; it reads
``claude_desktop_config.json`` on launch. Connecting means writing one entry
into that file and leaving everything else in it alone. This is the path for
people who use Claude in a window and have never opened Terminal.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

CLIENT_ID = "claude_desktop"
CLIENT_NAME = "Claude Desktop"
SERVER_NAME = "questboard"

_APP_BUNDLES = (
    Path("/Applications/Claude.app"),
    Path.home() / "Applications" / "Claude.app",
)

# Set after this process changed the file; Claude Desktop only rereads it on
# launch, so the person has to restart the app for the change to show.
_changed_this_session = False


def config_path() -> Path:
    override = os.environ.get("CLAUDE_DESKTOP_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def installed() -> bool:
    return any(bundle.exists() for bundle in _APP_BUNDLES)


def _read_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_config(config: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # A person's other servers live in this file; keep the previous copy.
        shutil.copyfile(path, path.with_suffix(".json.bak"))
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def _entry(runtime: list[str]) -> dict[str, Any]:
    return {"command": runtime[0], "args": list(runtime[1:])}


def is_connected(runtime: list[str]) -> bool:
    servers = _read_config().get("mcpServers")
    if not isinstance(servers, dict):
        return False
    current = servers.get(SERVER_NAME)
    return isinstance(current, dict) and current.get("command") == runtime[0]


def status(runtime: list[str]) -> dict[str, Any]:
    present = installed()
    return {
        "id": CLIENT_ID,
        "name": CLIENT_NAME,
        "installed": present,
        # A stale entry in a config file is not a connection if the app is gone.
        "connected": present and is_connected(runtime),
        "restart_required": _changed_this_session,
    }


def connect(runtime: list[str]) -> dict[str, Any]:
    global _changed_this_session
    if not installed():
        raise ValueError(
            f"{CLIENT_NAME} is not installed. Download it from claude.ai/download, open it once, then try again."
        )
    config = _read_config()
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[SERVER_NAME] = _entry(runtime)
    config["mcpServers"] = servers
    _write_config(config)
    _changed_this_session = True
    return status(runtime)


def disconnect(runtime: list[str]) -> dict[str, Any]:
    global _changed_this_session
    config = _read_config()
    servers = config.get("mcpServers")
    if isinstance(servers, dict) and SERVER_NAME in servers:
        del servers[SERVER_NAME]
        config["mcpServers"] = servers
        _write_config(config)
        _changed_this_session = True
    return status(runtime)
