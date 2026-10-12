"""Roles the assistant searched but the person never saved become a proposal.

refresh_work can run roles beyond the saved list while the board filters by
the saved list, so picks under those extra roles never showed (Oct 12 2026:
7 extra roles, ~12 "good" rows hidden). Recording them as a pending proposal
lets the person add them with one click; saved roles are never written here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services import workspace_service

SEARCHED_ROLES_RATIONALE = (
    "Your assistant searched these roles; they are not in your saved list yet."
)


def proposed_role_list(saved: list[str], searched: list[str], *, cap: int) -> list[str] | None:
    """Saved roles in saved order, then the unsaved searched ones, capped.

    None when the capped list adds nothing to the saved roles.
    """
    seen: set[str] = set()

    def fresh(roles: list[str]) -> list[str]:
        out: list[str] = []
        for role in roles:
            text = " ".join(str(role or "").split())
            if text and text.lower() not in seen:
                seen.add(text.lower())
                out.append(text)
        return out

    kept = fresh(saved)
    extras = fresh(searched)[: max(cap - len(kept), 0)]
    return kept + extras if extras else None


def propose_searched_roles(
    db: Session, roles: list[str], *, workspace_id: str | None = None
) -> dict[str, Any] | None:
    from app.services import local_agent_service

    workspace = local_agent_service.resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return None
    saved = list(workspace_service.get_workspace_preferences(db, workspace.id).roles)
    proposed = proposed_role_list(saved, roles or [], cap=local_agent_service.ROLES_CAP)
    if proposed is None:
        return None
    return local_agent_service.propose_career_preferences(
        db,
        proposed,
        SEARCHED_ROLES_RATIONALE,
        workspace_id=workspace.id,
    )
