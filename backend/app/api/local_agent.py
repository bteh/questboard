"""Local desktop endpoints for the agent integration.

The resume-consent endpoints let the Questboard app grant or revoke the
connected agent's access to the local resume from Settings, so a person does
not have to run the `make agent-consent-grant` CLI. This is a HUMAN surface
(the desktop UI calls it); the stdio MCP server exposes no consent tool, so an
agent using only Questboard MCP tools still cannot grant itself access.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.resume import AgentConsentRequest, AgentConsentStatus
from app.services import local_agent_service, resume_consent

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/resume-consent", response_model=AgentConsentStatus)
def get_agent_consent(db: Session = Depends(get_db)) -> AgentConsentStatus:
    workspace = local_agent_service.resolve_local_workspace(db)
    if workspace is None:
        return AgentConsentStatus(granted=False)
    return AgentConsentStatus(**resume_consent.status(workspace.id))


@router.post("/resume-consent", response_model=AgentConsentStatus)
def set_agent_consent(
    payload: AgentConsentRequest, db: Session = Depends(get_db)
) -> AgentConsentStatus:
    workspace = local_agent_service.resolve_local_workspace(db)
    if workspace is None:
        raise HTTPException(
            status_code=400, detail="No local profile to grant resume access for"
        )
    if payload.grant:
        resume_consent.grant(workspace.id, ttl_hours=payload.ttl_hours)
    else:
        resume_consent.revoke(workspace.id)
    return AgentConsentStatus(**resume_consent.status(workspace.id))
