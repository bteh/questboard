"""Lightweight in-memory security helpers for hosted APIs."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

_WINDOWS: dict[str, deque[float]] = {}


def _prune(bucket: deque[float], window_seconds: int) -> None:
    cutoff = time.time() - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def request_identity(request: Request, workspace_id: str | None = None) -> str:
    if workspace_id:
        return f"ws:{workspace_id}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def enforce_rate_limit(
    bucket_name: str,
    identity: str,
    *,
    limit: int,
    window_seconds: int = 60,
    db: Session | None = None,
) -> None:
    if db is not None:
        from app.models.rate_limit import RateLimitEvent

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        db.query(RateLimitEvent).filter(RateLimitEvent.created_at < cutoff).delete(
            synchronize_session=False
        )
        current = (
            db.query(func.count(RateLimitEvent.id))
            .filter(
                RateLimitEvent.bucket_name == bucket_name,
                RateLimitEvent.identity == identity,
                RateLimitEvent.created_at >= cutoff,
            )
            .scalar()
            or 0
        )
        if current >= limit:
            db.commit()
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        db.add(
            RateLimitEvent(
                bucket_name=bucket_name,
                identity=identity,
            )
        )
        db.commit()
        return

    key = f"{bucket_name}:{identity}"
    bucket = _WINDOWS.setdefault(key, deque())
    _prune(bucket, window_seconds)
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(time.time())
