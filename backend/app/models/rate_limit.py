"""Database-backed rate limit events for hosted deployments."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.models.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bucket_name = Column(String(80), nullable=False, index=True)
    identity = Column(String(128), nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow, nullable=False, index=True)
