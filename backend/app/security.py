"""Lightweight in-memory security helpers for hosted APIs."""

from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request

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
) -> None:
    key = f"{bucket_name}:{identity}"
    bucket = _WINDOWS.setdefault(key, deque())
    _prune(bucket, window_seconds)
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(time.time())
