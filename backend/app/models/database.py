"""Database connection management for the FastAPI backend."""

from __future__ import annotations

import logging
import os
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, close_all_sessions, sessionmaker

# Import Base from src — single source of truth for ORM models
from job_finder.models.database import Base  # noqa: F401

from app.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _add_missing_columns(engine, table_name: str, migrations: list[tuple[str, str]]) -> None:
    insp = inspect(engine)
    if table_name not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(table_name)}
    pending = [(col, sql) for col, sql in migrations if col not in existing]
    if not pending:
        return
    with engine.begin() as conn:
        for col, sql in pending:
            logger.info("Migrating %s: adding column %s", table_name, col)
            conn.execute(text(sql))


def _migrate_db(engine) -> None:
    """Add missing columns to existing tables (lightweight migration).

    Delegates to src's migration logic where possible, but also runs
    any backend-specific migrations.
    """
    insp = inspect(engine)

    if "applications" in insp.get_table_names():
        _add_missing_columns(engine, "applications", [
            ("profile", "ALTER TABLE applications ADD COLUMN profile VARCHAR(100) DEFAULT 'default'"),
            ("company_type", "ALTER TABLE applications ADD COLUMN company_type VARCHAR(50) DEFAULT 'Unknown'"),
            ("work_type", "ALTER TABLE applications ADD COLUMN work_type VARCHAR(20) DEFAULT ''"),
            ("workspace_id", "ALTER TABLE applications ADD COLUMN workspace_id VARCHAR(64)"),
            ("salary_currency", "ALTER TABLE applications ADD COLUMN salary_currency VARCHAR(16) DEFAULT ''"),
            ("salary_period", "ALTER TABLE applications ADD COLUMN salary_period VARCHAR(20) DEFAULT ''"),
            ("salary_min_annualized", "ALTER TABLE applications ADD COLUMN salary_min_annualized FLOAT"),
            ("salary_max_annualized", "ALTER TABLE applications ADD COLUMN salary_max_annualized FLOAT"),
            ("evaluation_report_json", "ALTER TABLE applications ADD COLUMN evaluation_report_json TEXT DEFAULT ''"),
        ])
        with engine.begin() as conn:
            # Convert empty job_url strings to NULL (allows multiple NULLs in unique column)
            conn.execute(text("UPDATE applications SET job_url = NULL WHERE job_url = ''"))

    _add_missing_columns(engine, "workspace_preferences", [
        ("llm_provider", "ALTER TABLE workspace_preferences ADD COLUMN llm_provider VARCHAR(100) DEFAULT ''"),
        ("llm_base_url", "ALTER TABLE workspace_preferences ADD COLUMN llm_base_url VARCHAR(500) DEFAULT ''"),
        ("llm_api_key", "ALTER TABLE workspace_preferences ADD COLUMN llm_api_key TEXT DEFAULT ''"),
        ("llm_model", "ALTER TABLE workspace_preferences ADD COLUMN llm_model VARCHAR(255) DEFAULT ''"),
        ("target_companies_json", "ALTER TABLE workspace_preferences ADD COLUMN target_companies_json TEXT DEFAULT '[]'"),
        ("include_linkedin_jobs", "ALTER TABLE workspace_preferences ADD COLUMN include_linkedin_jobs BOOLEAN DEFAULT 0"),
    ])
    with engine.begin() as conn:
        if "workspace_preferences" in insp.get_table_names():
            conn.execute(text("UPDATE workspace_preferences SET target_companies_json = COALESCE(target_companies_json, '[]')"))
            conn.execute(text("UPDATE workspace_preferences SET include_linkedin_jobs = COALESCE(include_linkedin_jobs, 0)"))

    _add_missing_columns(engine, "workspaces", [
        ("owner_user_id", "ALTER TABLE workspaces ADD COLUMN owner_user_id VARCHAR(128)"),
        ("name", "ALTER TABLE workspaces ADD COLUMN name VARCHAR(255) DEFAULT ''"),
        ("slug", "ALTER TABLE workspaces ADD COLUMN slug VARCHAR(255) DEFAULT ''"),
        ("plan", "ALTER TABLE workspaces ADD COLUMN plan VARCHAR(32) DEFAULT 'free'"),
        ("subscription_status", "ALTER TABLE workspaces ADD COLUMN subscription_status VARCHAR(32) DEFAULT 'inactive'"),
    ])
    with engine.begin() as conn:
        if "workspaces" in insp.get_table_names():
            conn.execute(text("UPDATE workspaces SET name = COALESCE(NULLIF(name, ''), 'Workspace')"))
            conn.execute(text("UPDATE workspaces SET slug = COALESCE(NULLIF(slug, ''), id)"))
            conn.execute(text("UPDATE workspaces SET plan = COALESCE(NULLIF(plan, ''), 'free')"))
            conn.execute(text(
                "UPDATE workspaces SET subscription_status = COALESCE(NULLIF(subscription_status, ''), 'inactive')"
            ))

    _add_missing_columns(engine, "workspace_resumes", [
        ("file_asset_id", "ALTER TABLE workspace_resumes ADD COLUMN file_asset_id INTEGER"),
        ("storage_provider", "ALTER TABLE workspace_resumes ADD COLUMN storage_provider VARCHAR(32) DEFAULT 'local'"),
        ("storage_path", "ALTER TABLE workspace_resumes ADD COLUMN storage_path VARCHAR(2000) DEFAULT ''"),
        ("file_sha256", "ALTER TABLE workspace_resumes ADD COLUMN file_sha256 VARCHAR(64) DEFAULT ''"),
    ])
    with engine.begin() as conn:
        if "workspace_resumes" in insp.get_table_names():
            conn.execute(text(
                "UPDATE workspace_resumes SET storage_provider = COALESCE(NULLIF(storage_provider, ''), 'local')"
            ))
            conn.execute(text("UPDATE workspace_resumes SET storage_path = COALESCE(storage_path, '')"))
            conn.execute(text("UPDATE workspace_resumes SET file_sha256 = COALESCE(file_sha256, '')"))

    _add_missing_columns(engine, "workspace_search_runs", [
        ("request_json", "ALTER TABLE workspace_search_runs ADD COLUMN request_json TEXT DEFAULT '{}'"),
        ("attempt_count", "ALTER TABLE workspace_search_runs ADD COLUMN attempt_count INTEGER DEFAULT 0"),
        ("max_attempts", "ALTER TABLE workspace_search_runs ADD COLUMN max_attempts INTEGER DEFAULT 3"),
        ("available_at", "ALTER TABLE workspace_search_runs ADD COLUMN available_at DATETIME"),
        ("claimed_by", "ALTER TABLE workspace_search_runs ADD COLUMN claimed_by VARCHAR(255) DEFAULT ''"),
        ("claimed_at", "ALTER TABLE workspace_search_runs ADD COLUMN claimed_at DATETIME"),
        ("lease_expires_at", "ALTER TABLE workspace_search_runs ADD COLUMN lease_expires_at DATETIME"),
        ("heartbeat_at", "ALTER TABLE workspace_search_runs ADD COLUMN heartbeat_at DATETIME"),
        ("created_at", "ALTER TABLE workspace_search_runs ADD COLUMN created_at DATETIME"),
        ("updated_at", "ALTER TABLE workspace_search_runs ADD COLUMN updated_at DATETIME"),
    ])
    with engine.begin() as conn:
        if "workspace_search_runs" in insp.get_table_names():
            conn.execute(text("UPDATE workspace_search_runs SET request_json = COALESCE(request_json, '{}')"))
            conn.execute(text("UPDATE workspace_search_runs SET attempt_count = COALESCE(attempt_count, 0)"))
            conn.execute(text("UPDATE workspace_search_runs SET max_attempts = COALESCE(max_attempts, 3)"))
            conn.execute(text(
                "UPDATE workspace_search_runs "
                "SET available_at = COALESCE(available_at, started_at, CURRENT_TIMESTAMP)"
            ))
            conn.execute(text("UPDATE workspace_search_runs SET claimed_by = COALESCE(claimed_by, '')"))
            conn.execute(text(
                "UPDATE workspace_search_runs "
                "SET created_at = COALESCE(created_at, started_at, CURRENT_TIMESTAMP)"
            ))
            conn.execute(text(
                "UPDATE workspace_search_runs "
                "SET updated_at = COALESCE(updated_at, completed_at, started_at, CURRENT_TIMESTAMP)"
            ))


def init_db(db_path: str | None = None) -> None:
    global _engine, _SessionLocal
    settings = get_settings()
    close_all_sessions()
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _SessionLocal = None
    if db_path and "://" not in db_path:
        database_url = f"sqlite:///{db_path}"
    else:
        database_url = db_path or settings.resolved_database_url
    using_sqlite = database_url.startswith("sqlite:///")
    if using_sqlite:
        path = database_url.removeprefix("sqlite:///")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        engine_kwargs = {
            "echo": False,
            "connect_args": {"check_same_thread": False},
        }
    else:
        engine_kwargs = {
            "echo": False,
            "pool_pre_ping": True,
        }

    _engine = create_engine(database_url, **engine_kwargs)
    # Import models to register them with Base.metadata
    from app.models.application import ApplicationRecord  # noqa: F401
    from app.models.rate_limit import RateLimitEvent  # noqa: F401
    from app.models.schedule import Schedule  # noqa: F401
    from app.models.workspace import (  # noqa: F401
        FileAsset,
        Profile,
        UsageCounter,
        WorkerHeartbeat,
        Workspace,
        WorkspaceMembership,
        WorkspacePreferences,
        WorkspaceResume,
        WorkspaceSearchEvent,
        WorkspaceSearchRun,
        WorkspaceSession,
    )

    if settings.should_manage_schema_on_startup:
        Base.metadata.create_all(_engine)
        if using_sqlite:
            _migrate_db(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_db() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
