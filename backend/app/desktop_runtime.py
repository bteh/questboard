"""Local desktop runtime entrypoint for Launchboard."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def desktop_cors_origins(dev_origin: str | None = None) -> list[str]:
    origins = [
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "tauri://localhost",
        "https://tauri.localhost",
    ]
    if dev_origin:
        origins.append(dev_origin.rstrip("/"))
    return origins


def configure_desktop_environment(
    *,
    data_dir: Path,
    workspace_storage_dir: Path,
    resume_dir: Path,
    config_dir: Path,
    dev_origin: str | None = None,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_storage_dir.mkdir(parents=True, exist_ok=True)
    resume_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    os.environ["HOSTED_MODE"] = "false"
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["WORKSPACE_STORAGE_DIR"] = str(workspace_storage_dir)
    os.environ["RESUME_DIR"] = str(resume_dir)
    os.environ["CONFIG_DIR"] = str(config_dir)
    os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
    os.environ["EMBEDDED_SCHEDULER_ENABLED"] = "true"
    os.environ["CORS_ORIGINS"] = ",".join(desktop_cors_origins(dev_origin))
    os.environ["LAUNCHBOARD_DESKTOP_MODE"] = "true"


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_data_dir = repo_root / "data" / "desktop"
    default_workspace_dir = default_data_dir / "workspaces"
    default_resume_dir = repo_root / "knowledge"
    default_config_dir = repo_root / "src" / "job_finder" / "config"

    parser = argparse.ArgumentParser(description="Launchboard desktop runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--data-dir", default=str(default_data_dir))
    parser.add_argument("--workspace-storage-dir", default=str(default_workspace_dir))
    parser.add_argument("--resume-dir", default=str(default_resume_dir))
    parser.add_argument("--config-dir", default=str(default_config_dir))
    parser.add_argument("--dev-origin", default="http://127.0.0.1:5173")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_desktop_environment(
        data_dir=Path(args.data_dir),
        workspace_storage_dir=Path(args.workspace_storage_dir),
        resume_dir=Path(args.resume_dir),
        config_dir=Path(args.config_dir),
        dev_origin=args.dev_origin,
    )
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
