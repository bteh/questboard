"""Database connection management for the FastAPI backend.

Uses src/job_finder's Base and ApplicationRecord as the single source of truth
for the ORM model. This module provides engine/session management and the
get_db() dependency for FastAPI route injection.
"""

from __future__ import annotations

import logging
import os
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

# Import Base from src — single source of truth for ORM models
from job_finder.models.database import Base  # noqa: F401

from app.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def _migrate_db(engine) -> None:
    """Add missing columns to existing tables (lightweight migration).

    Delegates to src's migration logic where possible, but also runs
    any backend-specific migrations.
    """
    insp = inspect(engine)
    if "applications" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("applications")}
    migrations: list[tuple[str, str]] = [
        ("profile", "ALTER TABLE applications ADD COLUMN profile VARCHAR(100) DEFAULT 'default'"),
        ("company_type", "ALTER TABLE applications ADD COLUMN company_type VARCHAR(50) DEFAULT 'Unknown'"),
        ("work_type", "ALTER TABLE applications ADD COLUMN work_type VARCHAR(20) DEFAULT ''"),
        ("workspace_id", "ALTER TABLE applications ADD COLUMN workspace_id VARCHAR(64)"),
        ("salary_currency", "ALTER TABLE applications ADD COLUMN salary_currency VARCHAR(16) DEFAULT ''"),
        ("salary_period", "ALTER TABLE applications ADD COLUMN salary_period VARCHAR(20) DEFAULT ''"),
        ("salary_min_annualized", "ALTER TABLE applications ADD COLUMN salary_min_annualized FLOAT"),
        ("salary_max_annualized", "ALTER TABLE applications ADD COLUMN salary_max_annualized FLOAT"),
    ]
    with engine.begin() as conn:
        for col, sql in migrations:
            if col not in existing:
                logger.info("Migrating: adding column %s", col)
                conn.execute(text(sql))
        # Convert empty job_url strings to NULL (allows multiple NULLs in unique column)
        conn.execute(text("UPDATE applications SET job_url = NULL WHERE job_url = ''"))

    if "workspace_preferences" in insp.get_table_names():
        workspace_existing = {c["name"] for c in insp.get_columns("workspace_preferences")}
        workspace_migrations: list[tuple[str, str]] = [
            ("llm_provider", "ALTER TABLE workspace_preferences ADD COLUMN llm_provider VARCHAR(100) DEFAULT ''"),
            ("llm_base_url", "ALTER TABLE workspace_preferences ADD COLUMN llm_base_url VARCHAR(500) DEFAULT ''"),
            ("llm_api_key", "ALTER TABLE workspace_preferences ADD COLUMN llm_api_key TEXT DEFAULT ''"),
            ("llm_model", "ALTER TABLE workspace_preferences ADD COLUMN llm_model VARCHAR(255) DEFAULT ''"),
        ]
        with engine.begin() as conn:
            for col, sql in workspace_migrations:
                if col not in workspace_existing:
                    logger.info("Migrating workspace_preferences: adding column %s", col)
                    conn.execute(text(sql))


def init_db(db_path: str | None = None) -> None:
    global _engine, _SessionLocal
    settings = get_settings()
    path = db_path or settings.db_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # Import models to register them with Base.metadata
    from app.models.application import ApplicationRecord  # noqa: F401
    from app.models.schedule import Schedule  # noqa: F401
    from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume, WorkspaceSearchRun, WorkspaceSession  # noqa: F401

    Base.metadata.create_all(_engine)
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
