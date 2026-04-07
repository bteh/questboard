from __future__ import annotations

import os
from pathlib import Path

from app.desktop_runtime import configure_desktop_environment, desktop_cors_origins


def test_desktop_cors_origins_include_tauri_and_dev_server() -> None:
    origins = desktop_cors_origins("http://127.0.0.1:5173")
    assert "http://127.0.0.1:1420" in origins
    assert "https://tauri.localhost" in origins
    assert "http://127.0.0.1:5173" in origins


def test_configure_desktop_environment_sets_local_runtime_paths(tmp_path: Path, monkeypatch) -> None:
    for key in [
        "HOSTED_MODE",
        "DATA_DIR",
        "WORKSPACE_STORAGE_DIR",
        "RESUME_DIR",
        "CONFIG_DIR",
        "MANAGE_SCHEMA_ON_STARTUP",
        "EMBEDDED_SCHEDULER_ENABLED",
        "CORS_ORIGINS",
        "LAUNCHBOARD_DESKTOP_MODE",
    ]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "data"
    workspace_dir = data_dir / "workspaces"
    resume_dir = tmp_path / "knowledge"
    config_dir = tmp_path / "config"

    configure_desktop_environment(
        data_dir=data_dir,
        workspace_storage_dir=workspace_dir,
        resume_dir=resume_dir,
        config_dir=config_dir,
        dev_origin="http://127.0.0.1:5173",
    )

    assert os.environ["HOSTED_MODE"] == "false"
    assert os.environ["DATA_DIR"] == str(data_dir)
    assert os.environ["WORKSPACE_STORAGE_DIR"] == str(workspace_dir)
    assert os.environ["RESUME_DIR"] == str(resume_dir)
    assert os.environ["CONFIG_DIR"] == str(config_dir)
    assert os.environ["MANAGE_SCHEMA_ON_STARTUP"] == "true"
    assert os.environ["EMBEDDED_SCHEDULER_ENABLED"] == "true"
    assert os.environ["LAUNCHBOARD_DESKTOP_MODE"] == "true"
    assert "http://127.0.0.1:5173" in os.environ["CORS_ORIGINS"]
    assert data_dir.exists()
    assert workspace_dir.exists()
    assert resume_dir.exists()
    assert config_dir.exists()
