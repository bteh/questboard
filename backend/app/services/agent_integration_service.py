"""Detect and wire the user's MCP agent (Claude Code, Codex) from the app.

This is the in-app version of `make agent-install`: a human clicks "Connect"
in Settings and Questboard registers its local stdio MCP server with the
agent's own config (via `<client> mcp add`). It only edits the selected
client's config; it never installs a model, asks for a key, or opens a
network service. The MCP command points at the SAME runtime + data dir the
app is using, so the agent reads the same local board and resume.

GUI apps on macOS do not inherit the shell PATH, so `claude`/`codex` live in
places `shutil.which` won't find by default. We search the common install
dirs and run with an augmented PATH.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SERVER_NAME = "questboard"

# The MCP tools a headless run is allowed to call, without any interactive
# permission prompt. All are local read / local-preference writes; none can
# transact, message, or reach outside the machine (see the agent boundary in
# CLAUDE.md), so allow-listing them is safe and avoids --dangerously-skip.
RUN_ALLOWED_TOOLS: tuple[str, ...] = (
    "read_resume_for_matching",
    "get_career_preferences",
    "set_career_preferences",
    "search_work",
    "search_side_quests",
    "get_opportunity",
    "set_work_fit",
)

# id -> display name, in the order we show them.
CLIENTS: dict[str, str] = {"claude": "Claude Code", "codex": "Codex"}

# Where CLI agents commonly install, beyond whatever PATH the app inherited.
_EXTRA_BIN_DIRS = [
    Path.home() / ".local" / "bin",
    Path("/usr/local/bin"),
    Path("/opt/homebrew/bin"),
    Path.home() / ".cargo" / "bin",
    Path.home() / ".npm-global" / "bin",
    Path.home() / "bin",
]


def _augmented_env() -> dict[str, str]:
    env = dict(os.environ)
    extra = os.pathsep.join(str(d) for d in _EXTRA_BIN_DIRS if d.is_dir())
    env["PATH"] = f"{extra}{os.pathsep}{env.get('PATH', '')}" if extra else env.get("PATH", "")
    # When we're the frozen (PyInstaller) sidecar, the loader vars it injected
    # would break a spawned Node binary like `claude`. PyInstaller keeps each
    # original in `<VAR>_ORIG`; restore those, drop ours, so the child sees a
    # clean environment.
    if getattr(sys, "frozen", False):
        for var in ("DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "LD_LIBRARY_PATH"):
            original = env.pop(f"{var}_ORIG", None)
            if original is not None:
                env[var] = original
            else:
                env.pop(var, None)
    return env


def resolve_binary(client: str) -> str | None:
    """Absolute path to the client CLI, searching PATH then common dirs."""
    found = shutil.which(client, path=_augmented_env()["PATH"])
    if found:
        return found
    for directory in _EXTRA_BIN_DIRS:
        candidate = directory / client
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or (Path.cwd() / "backend" / "data")).resolve()


def runtime_command() -> list[str]:
    """The MCP server command for the runtime the app is currently running.

    Packaged (frozen) app: the bundled runtime binary in `--mcp` mode, wired to
    the app's data/workspace/resume/config dirs (matching main.rs). Source
    checkout: the venv `questboard-mcp` entrypoint against backend/data.
    """
    data_dir = _data_dir()
    if getattr(sys, "frozen", False):
        app_data = data_dir.parent
        return [
            sys.executable,
            "--mcp",
            "--data-dir",
            str(data_dir),
            "--workspace-storage-dir",
            str(data_dir / "workspaces"),
            "--resume-dir",
            str(app_data / "knowledge"),
            "--config-dir",
            str(app_data / "config"),
        ]
    repo_root = Path(__file__).resolve().parents[3]
    exe = repo_root / ".venv" / ("Scripts/questboard-mcp.exe" if sys.platform == "win32" else "bin/questboard-mcp")
    return [str(exe), "--data-dir", str(data_dir)]


def _add_command(client: str, binary: str, runtime: list[str]) -> list[str]:
    if client == "codex":
        return [binary, "mcp", "add", SERVER_NAME, "--", *runtime]
    # claude
    return [binary, "mcp", "add", "--transport", "stdio", "--scope", "user", SERVER_NAME, "--", *runtime]


def _remove_command(client: str, binary: str) -> list[str]:
    if client == "claude":
        return [binary, "mcp", "remove", "--scope", "user", SERVER_NAME]
    return [binary, "mcp", "remove", SERVER_NAME]


def _is_connected(client: str, binary: str) -> bool:
    try:
        result = subprocess.run(
            [binary, "mcp", "get", SERVER_NAME],
            capture_output=True,
            text=True,
            env=_augmented_env(),
            timeout=15,
            check=False,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001 - a broken client CLI must not crash the app
        logger.warning("Could not read MCP status for %s", client, exc_info=True)
        return False


def client_status(client: str) -> dict[str, Any]:
    binary = resolve_binary(client)
    return {
        "id": client,
        "name": CLIENTS[client],
        "installed": binary is not None,
        "connected": bool(binary and _is_connected(client, binary)),
    }


def list_clients() -> list[dict[str, Any]]:
    return [client_status(client) for client in CLIENTS]


def connect(client: str) -> dict[str, Any]:
    if client not in CLIENTS:
        raise ValueError(f"Unknown assistant: {client}")
    binary = resolve_binary(client)
    if binary is None:
        raise ValueError(
            f"{CLIENTS[client]} is not installed, or Questboard can’t find it. "
            "Install it, then try again."
        )
    runtime = runtime_command()
    env = _augmented_env()
    try:
        # Replace any stale entry so a re-connect always points at the current runtime.
        if _is_connected(client, binary):
            subprocess.run(_remove_command(client, binary), capture_output=True, text=True, env=env, timeout=30, check=False)
        result = subprocess.run(
            _add_command(client, binary, runtime),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{CLIENTS[client]} did not respond in time. Try again.")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:400]
        raise RuntimeError(f"Could not connect {CLIENTS[client]}: {detail or 'unknown error'}")
    return {**client_status(client), "restart_required": True}


def disconnect(client: str) -> dict[str, Any]:
    if client not in CLIENTS:
        raise ValueError(f"Unknown assistant: {client}")
    binary = resolve_binary(client)
    if binary is None:
        return client_status(client)
    try:
        subprocess.run(
            _remove_command(client, binary),
            capture_output=True,
            text=True,
            env=_augmented_env(),
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{CLIENTS[client]} did not respond in time. Try again.")
    return client_status(client)


def _mcp_config_json() -> str:
    """An --mcp-config document wiring the client to the app's Questboard MCP,
    the same runtime + data dir the app itself uses."""
    runtime = runtime_command()
    return json.dumps(
        {"mcpServers": {SERVER_NAME: {"type": "stdio", "command": runtime[0], "args": runtime[1:]}}}
    )


def _run_command(client: str, binary: str, prompt: str, config_path: str, allowed: list[str]) -> list[str]:
    qualified = [f"mcp__{SERVER_NAME}__{tool}" for tool in allowed]
    if client == "claude":
        return [
            binary, "-p", prompt,
            "--mcp-config", config_path,
            "--allowedTools", ",".join(qualified),
            # Sonnet is much faster than Opus and plenty for mapping postings to
            # a resume; the run is a ranking task, not open-ended reasoning.
            "--model", "sonnet",
            "--output-format", "json",
        ]
    # codex exec: non-interactive, reads its own ~/.codex MCP registration.
    return [binary, "exec", "--skip-git-repo-check", prompt]


def run_headless(
    client: str,
    prompt: str,
    allowed_tools: list[str] | None = None,
    *,
    timeout: int = 300,
) -> dict[str, Any]:
    """Run the user's own agent once, non-interactively, driving the Questboard
    MCP tools, and return its final answer.

    This is how the app makes the AI step seamless: instead of the user pasting
    a prompt into Claude/Codex, the app spawns the CLI in print mode pointed at
    the same local MCP server. It uses the user's own agent auth, so Questboard
    funds no inference. Only the local Questboard tools are allow-listed, so the
    run never needs a blanket permission bypass.

    Returns {ok, result, error, cost_usd, num_turns}. Never raises for an agent
    failure — the caller renders `error` to the user.
    """
    if get_settings_hosted():
        raise RuntimeError("Headless agent runs are not available in hosted mode")
    if client not in CLIENTS:
        raise ValueError(f"Unknown assistant: {client}")
    binary = resolve_binary(client)
    if binary is None:
        return {"ok": False, "result": "", "error": f"{CLIENTS[client]} is not installed.", "cost_usd": None, "num_turns": None}
    if client == "codex":
        # Codex exec doesn't take an inline --mcp-config or an allow-list flag,
        # so a headless run can't be pinned to the Questboard tools safely yet.
        return {
            "ok": False, "result": "",
            "error": "Automatic runs support Claude Code today. For Codex, use the copyable prompt.",
            "cost_usd": None, "num_turns": None,
        }

    allowed = list(allowed_tools or RUN_ALLOWED_TOOLS)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", prefix="qb-mcp-", delete=False)
    try:
        tmp.write(_mcp_config_json())
        tmp.close()
        command = _run_command(client, binary, prompt, tmp.name, allowed)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=_augmented_env(),
            stdin=subprocess.DEVNULL,  # print mode waits ~3s on stdin otherwise
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "result": "", "error": f"{CLIENTS[client]} ran past {timeout}s and was stopped.", "cost_usd": None, "num_turns": None}
    except Exception:  # noqa: BLE001 - a broken CLI must not crash the app
        logger.warning("Headless run failed for %s", client, exc_info=True)
        return {"ok": False, "result": "", "error": f"Could not run {CLIENTS[client]}.", "cost_usd": None, "num_turns": None}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:400]
        return {"ok": False, "result": "", "error": detail or f"{CLIENTS[client]} exited with an error.", "cost_usd": None, "num_turns": None}

    return _parse_claude_json(result.stdout)


def _parse_claude_json(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        text = (stdout or "").strip()
        return {"ok": bool(text), "result": text, "error": "" if text else "No output.", "cost_usd": None, "num_turns": None}
    text = str(payload.get("result") or "").strip()
    is_error = bool(payload.get("is_error"))
    return {
        "ok": not is_error and bool(text),
        "result": text,
        "error": "" if (not is_error and text) else (text or "The assistant returned no answer."),
        "cost_usd": payload.get("total_cost_usd"),
        "num_turns": payload.get("num_turns"),
    }


def get_settings_hosted() -> bool:
    """Small indirection so the run path checks hosted mode without importing
    FastAPI settings at module load (keeps this service import-light)."""
    try:
        from app.config import get_settings

        return bool(get_settings().hosted_mode)
    except Exception:  # noqa: BLE001
        return False
