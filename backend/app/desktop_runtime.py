"""Local desktop runtime entrypoint for Questboard."""

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
    # Point the job_finder pipeline/scraper engine at the SAME sqlite file as
    # the app engine. In --mcp mode the FastAPI lifespan (which normally sets
    # these) never runs, so without this the pipeline logs scrape runs and
    # cadence to a different DB and get_source_status reads none of them.
    resolved_db = f"sqlite:///{data_dir / 'job_tracker.db'}"
    os.environ["DATABASE_URL"] = resolved_db
    os.environ["JOB_FINDER_DATABASE_URL"] = resolved_db
    os.environ["JOB_FINDER_DATA_DIR"] = str(data_dir)
    os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
    os.environ["CORS_ORIGINS"] = ",".join(desktop_cors_origins(dev_origin))
    os.environ["QUESTBOARD_DESKTOP_MODE"] = "true"


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_data_dir = repo_root / "data" / "desktop"
    default_workspace_dir = default_data_dir / "workspaces"
    default_resume_dir = repo_root / "knowledge"
    default_config_dir = repo_root / "src" / "job_finder" / "config"

    parser = argparse.ArgumentParser(description="Questboard desktop runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--data-dir", default=str(default_data_dir))
    parser.add_argument("--workspace-storage-dir", default=str(default_workspace_dir))
    parser.add_argument("--resume-dir", default=str(default_resume_dir))
    parser.add_argument("--config-dir", default=str(default_config_dir))
    parser.add_argument("--dev-origin", default="http://127.0.0.1:5173")
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run the local stdio MCP server instead of the desktop HTTP API",
    )
    parser.add_argument(
        "--check-jobspy-import",
        action="store_true",
        help="Verify the packaged JobSpy dependency without contacting job boards",
    )
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
    if args.mcp:
        # The packaged desktop sidecar doubles as the agent integration, so a
        # user installs one signed artifact rather than a second Python tool.
        from app.local_mcp import mcp
        from app.models.database import init_db
        from job_finder.tools.job_search_tool import preload_jobspy

        preload_jobspy()
        init_db()
        mcp.run(transport="stdio")
        return

    # Import only after the runtime directories have been installed in the
    # environment. This remains a real import (and is therefore visible to
    # PyInstaller) while ensuring every backend module resolves paths against
    # the user's app-data directory, never the build machine's checkout.
    from app.main import app as fastapi_app

    # Job pulls execute on background workers, but a frozen build must perform
    # JobSpy's first import on the main thread.  A failure remains non-fatal so
    # direct ATS/community sources still work; each JobSpy source will publish
    # the exact import error in its coverage receipt instead of vanishing.
    from job_finder.tools.job_search_tool import preload_jobspy

    jobspy_error = preload_jobspy()
    if args.check_jobspy_import:
        if jobspy_error:
            raise SystemExit(f"Packaged JobSpy import failed: {jobspy_error}")
        print("Packaged JobSpy import: ok")
        return

    uvicorn.run(fastapi_app, host=args.host, port=args.port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
