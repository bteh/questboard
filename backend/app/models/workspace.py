"""Hosted workspace models for anonymous web sessions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(64), primary_key=True)
    mode = Column(String(32), default="anonymous")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_active_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)


class WorkspaceSession(Base):
    __tablename__ = "workspace_sessions"

    id = Column(String(64), primary_key=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, index=True)
    session_token_hash = Column(String(128), nullable=False, unique=True, index=True)
    csrf_token_hash = Column(String(128), nullable=False)
    user_agent = Column(String(500), default="")
    ip_address = Column(String(128), default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_seen_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)


class WorkspaceResume(Base):
    __tablename__ = "workspace_resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, unique=True, index=True)
    original_filename = Column(String(500), default="")
    stored_filename = Column(String(255), default="")
    file_path = Column(String(2000), default="")
    text_path = Column(String(2000), default="")
    mime_type = Column(String(100), default="application/pdf")
    file_size = Column(Integer, default=0)
    parse_status = Column(String(50), default="missing")
    parse_warning = Column(Text, default="")
    extracted_text = Column(Text, default="")
    llm_summary = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class WorkspacePreferences(Base):
    __tablename__ = "workspace_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, unique=True, index=True)
    roles_json = Column(Text, default="[]")
    keywords_json = Column(Text, default="[]")
    preferred_places_json = Column(Text, default="[]")
    workplace_preference = Column(String(32), default="remote_friendly")
    max_days_old = Column(Integer, default=14)
    current_title = Column(String(300), default="")
    current_level = Column(String(50), default="mid")
    llm_provider = Column(String(100), default="")
    llm_base_url = Column(String(500), default="")
    llm_api_key = Column(Text, default="")
    llm_model = Column(String(255), default="")
    current_comp = Column(Float, nullable=True)
    compensation_currency = Column(String(8), default="USD")
    compensation_period = Column(String(20), default="annual")
    min_base = Column(Float, nullable=True)
    target_total_comp = Column(Float, nullable=True)
    min_acceptable_tc = Column(Float, nullable=True)
    include_equity = Column(Boolean, default=True)
    exclude_staffing_agencies = Column(Boolean, default=True)
    include_remote = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class WorkspaceSearchRun(Base):
    __tablename__ = "workspace_search_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, index=True)
    run_id = Column(String(32), nullable=False, unique=True, index=True)
    status = Column(String(32), default="pending")
    mode = Column(String(50), default="search_score")
    snapshot_json = Column(Text, default="{}")
    jobs_found = Column(Integer, default=0)
    jobs_scored = Column(Integer, default=0)
    strong_matches = Column(Integer, default=0)
    error = Column(Text, default="")
    started_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)
