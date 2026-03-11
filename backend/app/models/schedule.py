"""Schedule model — stores recurring search configuration per profile."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String

from app.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile = Column(String(100), unique=True, nullable=False)
    enabled = Column(Boolean, default=False)
    interval_hours = Column(Float, default=6.0)
    mode = Column(String(50), default="search_score")
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    last_run_jobs_found = Column(Integer, default=0)
    last_run_new_jobs = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
