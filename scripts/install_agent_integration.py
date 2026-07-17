"""Install Questboard's local MCP server into Codex and/or Claude Code.

The script changes only the selected client's user configuration.  It never
installs a model, requests an API key, or enables a remote Questboard service.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


SERVER_NAME = "questboard"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def desktop_runtime() -> tuple[list[str], str] | None:
    if sys.platform != "darwin":
        return None
    app_root = Path("/Applications/Questboard.app")
    binary = app_root / "Contents" / "Resources" / "sidecars" / "questboard-runtime"
    if not binary.exists():
        return None
    app_data = Path.home() / "Library" / "Application Support" / "com.questboard.desktop"
    data_dir = app_data / "runtime-data"
    command = [
        str(binary),
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
    return command, "installed Questboard.app"


def source_runtime() -> tuple[list[str], str]:
    root = repo_root()
    executable = root / ".venv" / ("Scripts/questboard-mcp.exe" if sys.platform == "win32" else "bin/questboard-mcp")
    if not executable.exists():
        raise SystemExit(
            "Questboard's MCP entrypoint is not installed. Run `make install` first."
        )
    return [str(executable), "--data-dir", str(root / "data")], "source checkout"


def resolve_runtime(preference: str) -> tuple[list[str], str]:
    if preference in {"auto", "desktop"}:
        desktop = desktop_runtime()
        if desktop is not None:
            return desktop
        if preference == "desktop":
            raise SystemExit("A packaged /Applications/Questboard.app runtime was not found")
    return source_runtime()


def add_command(client: str, server_command: list[str]) -> list[str]:
    if client == "codex":
        return ["codex", "mcp", "add", SERVER_NAME, "--", *server_command]
    if client == "claude":
        return [
            "claude",
            "mcp",
            "add",
            "--transport",
            "stdio",
            "--scope",
            "user",
            SERVER_NAME,
            "--",
            *server_command,
        ]
    raise ValueError(f"Unsupported client: {client}")


def get_command(client: str) -> list[str]:
    return [client, "mcp", "get", SERVER_NAME]


def remove_command(client: str) -> list[str]:
    if client == "claude":
        return [client, "mcp", "remove", "--scope", "user", SERVER_NAME]
    return [client, "mcp", "remove", SERVER_NAME]


def configured(client: str) -> bool:
    result = subprocess.run(
        get_command(client), capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def run(command: list[str], *, dry_run: bool) -> None:
    print(f"  {shlex.join(command)}")
    if not dry_run:
        subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install the Questboard local MCP integration")
    parser.add_argument(
        "--client", choices=("all", "codex", "claude"), default="all"
    )
    parser.add_argument(
        "--runtime", choices=("auto", "desktop", "source"), default="auto"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing Questboard MCP entry",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_command, runtime_label = resolve_runtime(args.runtime)
    requested = ["codex", "claude"] if args.client == "all" else [args.client]
    available = [client for client in requested if shutil.which(client)]
    if not available:
        raise SystemExit("Neither selected agent client is installed on PATH")

    print(f"Questboard MCP runtime: {runtime_label}")
    for client in available:
        exists = configured(client) if not args.dry_run else False
        if exists and not args.force:
            print(f"  {client}: already configured, left unchanged (use --force to replace)")
            continue
        if exists:
            run(remove_command(client), dry_run=args.dry_run)
        run(add_command(client, server_command), dry_run=args.dry_run)
        action = "would be configured" if args.dry_run else "configured"
        print(f"  {client}: {action}; restart the client before using Questboard")


if __name__ == "__main__":
    main()
