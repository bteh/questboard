"""Shared helpers for workspace naming and slug allocation."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.workspace import Workspace


def slugify_workspace_name(value: str) -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return candidate[:96] or "workspace"


def allocate_workspace_slug(
    db: Session,
    label: str,
    *,
    exclude_workspace_id: str | None = None,
) -> str:
    base = slugify_workspace_name(label)
    slug = base
    suffix = 1

    while True:
        query = db.query(Workspace.id).filter(Workspace.slug == slug)
        if exclude_workspace_id:
            query = query.filter(Workspace.id != exclude_workspace_id)
        if not query.first():
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def ensure_workspace_identity(
    db: Session,
    workspace: Workspace,
    *,
    label: str,
    fallback_name: str = "Workspace",
) -> Workspace:
    name = (workspace.name or "").strip() or label.strip() or fallback_name
    workspace.name = name

    if not (workspace.slug or "").strip():
        workspace.slug = allocate_workspace_slug(
            db,
            label or name or fallback_name,
            exclude_workspace_id=workspace.id,
        )

    return workspace
