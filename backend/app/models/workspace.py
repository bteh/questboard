"""Hosted workspace models for authenticated users and durable jobs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(64), primary_key=True)
    owner_user_id = Column(String(128), ForeignKey("profiles.id"), nullable=True, index=True)
    name = Column(String(255), default="")
    slug = Column(String(255), default="", unique=True)
    mode = Column(String(32), default="personal")
    plan = Column(String(32), default="free")
    subscription_status = Column(String(32), default="inactive")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_active_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=True)


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String(128), primary_key=True)
    email = Column(String(320), nullable=False, default="", index=True)
    full_name = Column(String(255), default="")
    avatar_url = Column(String(2000), default="")
    auth_provider = Column(String(64), default="supabase")
    email_verified = Column(Boolean, default=False)
    plan = Column(String(32), default="free")
    subscription_status = Column(String(32), default="inactive")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_seen_at = Column(DateTime, default=_utcnow)


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String(128), ForeignKey("profiles.id"), nullable=False, index=True)
    role = Column(String(32), default="owner")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


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
    file_asset_id = Column(Integer, ForeignKey("file_assets.id"), nullable=True)
    original_filename = Column(String(500), default="")
    stored_filename = Column(String(255), default="")
    file_path = Column(String(2000), default="")
    text_path = Column(String(2000), default="")
    storage_provider = Column(String(32), default="local")
    storage_path = Column(String(2000), default="")
    file_sha256 = Column(String(64), default="")
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
    target_companies_json = Column(Text, default="[]")
    preferred_places_json = Column(Text, default="[]")
    workplace_preference = Column(String(32), default="remote_friendly")
    max_days_old = Column(Integer, default=14)
    include_linkedin_jobs = Column(Boolean, default=False)
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
    request_json = Column(Text, default="{}")
    jobs_found = Column(Integer, default=0)
    jobs_scored = Column(Integer, default=0)
    strong_matches = Column(Integer, default=0)
    error = Column(Text, default="")
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    available_at = Column(DateTime, default=_utcnow, index=True)
    claimed_by = Column(String(255), default="")
    claimed_at = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class WorkspaceSearchEvent(Base):
    __tablename__ = "workspace_search_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, index=True)
    run_id = Column(String(32), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    payload = Column(Text, default="")
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)


class FileAsset(Base):
    __tablename__ = "file_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, index=True)
    owner_user_id = Column(String(128), ForeignKey("profiles.id"), nullable=True, index=True)
    kind = Column(String(64), default="resume")
    storage_provider = Column(String(32), default="local")
    bucket = Column(String(255), default="")
    storage_path = Column(String(2000), default="")
    original_filename = Column(String(500), default="")
    mime_type = Column(String(100), default="application/octet-stream")
    byte_size = Column(Integer, default=0)
    sha256 = Column(String(64), default="")
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False, index=True)
    metric = Column(String(64), nullable=False, index=True)
    period_key = Column(String(64), nullable=False, index=True)
    used_count = Column(Integer, default=0)
    limit_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id = Column(String(255), primary_key=True)
    worker_type = Column(String(64), default="search")
    status = Column(String(32), default="idle")
    last_seen_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
    metadata_json = Column(Text, default="{}")
