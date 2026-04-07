"""Storage adapter for hosted Supabase buckets and local development files."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import requests

from app.config import get_settings


@dataclass
class StoredObject:
    storage_provider: str
    bucket: str
    storage_path: str
    local_path: str
    mime_type: str
    byte_size: int
    sha256: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _local_workspace_root(workspace_id: str) -> Path:
    return Path(get_settings().resolved_workspace_storage_dir) / workspace_id


def uses_managed_storage() -> bool:
    settings = get_settings()
    return bool(settings.hosted_mode and settings.supabase_url and settings.supabase_service_role_key)


def _storage_headers(content_type: str | None = None) -> dict[str, str]:
    settings = get_settings()
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    if content_type:
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "true"
    return headers


def _storage_base_url() -> str:
    settings = get_settings()
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/object"


def save_workspace_file(
    workspace_id: str,
    *,
    kind: str,
    original_filename: str,
    content: bytes,
    mime_type: str | None = None,
) -> StoredObject:
    resolved_mime = mime_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    digest = _sha256(content)
    clean_name = Path(original_filename).name or f"{kind}.bin"
    storage_path = f"workspaces/{workspace_id}/{kind}/{uuid.uuid4().hex}-{clean_name}"

    if not uses_managed_storage():
        root = _local_workspace_root(workspace_id)
        root.mkdir(parents=True, exist_ok=True)
        file_path = root / f"{uuid.uuid4().hex}-{clean_name}"
        file_path.write_bytes(content)
        return StoredObject(
            storage_provider="local",
            bucket="",
            storage_path=str(file_path),
            local_path=str(file_path),
            mime_type=resolved_mime,
            byte_size=len(content),
            sha256=digest,
        )

    settings = get_settings()
    response = requests.post(
        f"{_storage_base_url()}/{settings.supabase_storage_bucket}/{storage_path}",
        headers=_storage_headers(resolved_mime),
        data=content,
        timeout=30,
    )
    response.raise_for_status()
    return StoredObject(
        storage_provider="supabase",
        bucket=settings.supabase_storage_bucket,
        storage_path=storage_path,
        local_path="",
        mime_type=resolved_mime,
        byte_size=len(content),
        sha256=digest,
    )


def delete_object(*, bucket: str, storage_path: str, local_path: str = "") -> None:
    if local_path:
        try:
            Path(local_path).unlink(missing_ok=True)
        except Exception:
            pass
        return
    if not bucket or not storage_path or not uses_managed_storage():
        return
    requests.delete(
        f"{_storage_base_url()}/{bucket}/{storage_path}",
        headers=_storage_headers(),
        timeout=30,
    ).raise_for_status()


def read_object_bytes(*, bucket: str, storage_path: str, local_path: str = "") -> bytes:
    if local_path:
        return Path(local_path).read_bytes()
    response = requests.get(
        f"{_storage_base_url()}/{bucket}/{storage_path}",
        headers=_storage_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def materialize_object(*, bucket: str, storage_path: str, local_path: str = "", suffix: str = "") -> str:
    if local_path:
        return local_path
    payload = read_object_bytes(bucket=bucket, storage_path=storage_path, local_path=local_path)
    runtime_dir = Path(get_settings().data_dir) / "runtime" / "files"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=suffix or Path(storage_path).suffix,
        prefix="launchboard-",
        dir=runtime_dir,
        delete=False,
    )
    with handle:
        handle.write(payload)
    return handle.name
