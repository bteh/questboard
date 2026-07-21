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

from app.config import get_settings
from app.models.database import get_db
from app.schemas.resume import (
    AgentClientsResponse,
    AgentClientStatus,
    AgentConnectRequest,
    AgentConsentRequest,
    AgentConsentStatus,
    AgentRunRequest,
    AgentRunResponse,
)
from app.services import agent_integration_service, local_agent_service, resume_consent

router = APIRouter(prefix="/agent", tags=["agent"])

# Server-owned task prompts. The client sends only a task id, so it can't inject
# an arbitrary prompt or widen the tool allow-list. Each entry says whether the
# task needs the resume (and therefore resume consent).
_AGENT_TASKS: dict[str, dict[str, object]] = {
    "find_and_rank": {
        "needs_resume": True,
        "prompt": (
            "Use the Questboard MCP tools. First call read_resume_for_matching to read my "
            "resume, then get_career_preferences for my saved target roles. If my target "
            "roles are empty or clearly off, call set_career_preferences to set sharper ones "
            "from my resume. Then call search_work to find matching jobs. Retrieval order is "
            "not a fit verdict, so map each candidate against my actual background. "
            "Then call set_work_fit ONCE and give EVERY candidate search_work returned its own "
            "verdict, so my whole board is scored, not just the top few. Verdict scale: "
            "strong / good / reach for ones worth my time, skip for ones that don't fit "
            "(wrong role, staffing agency, junk). Rank the non-skips 1..N best-first; skips "
            "need no rank. Keep it FAST: each 'why' is a short phrase (a few words, <=12), and "
            "add a 'caveat' only when there's a real risk (wrong level, comp floor, remote "
            "unclear). Each needs its opportunity_id. set_work_fit is what puts your verdicts "
            "on my board. After that, reply with just a one-line summary (e.g. 'Scored 28: 6 "
            "strong/good, rest reach or skip; GitLab EM is #1.'). Be honest; don't invent postings."
        ),
    },
}


def _require_local() -> None:
    """Agent wiring runs local shell commands (`claude mcp add`); it must never
    be reachable on a hosted server."""
    if get_settings().hosted_mode:
        raise HTTPException(status_code=404, detail="Not available in hosted mode")


@router.get("/clients", response_model=AgentClientsResponse)
def get_agent_clients() -> AgentClientsResponse:
    """Which MCP assistants are installed and whether Questboard is wired in."""
    _require_local()
    return AgentClientsResponse(
        clients=[AgentClientStatus(**c) for c in agent_integration_service.list_clients()]
    )


@router.post("/connect", response_model=AgentClientStatus)
def connect_agent(payload: AgentConnectRequest) -> AgentClientStatus:
    """Register Questboard's local MCP server with the chosen assistant."""
    _require_local()
    try:
        return AgentClientStatus(**agent_integration_service.connect(payload.client))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/disconnect", response_model=AgentClientStatus)
def disconnect_agent(payload: AgentConnectRequest) -> AgentClientStatus:
    """Remove Questboard's MCP server from the chosen assistant."""
    _require_local()
    try:
        return AgentClientStatus(**agent_integration_service.disconnect(payload.client))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/run", response_model=AgentRunResponse)
def run_agent(payload: AgentRunRequest, db: Session = Depends(get_db)) -> AgentRunResponse:
    """Run the connected assistant once, headlessly, to do the AI step in-app.

    The user never opens their agent: the app spawns the CLI in print mode
    against the Questboard MCP tools and returns the answer. Uses the user's own
    agent auth, so Questboard funds no inference.
    """
    _require_local()
    task = _AGENT_TASKS.get(payload.task)
    if task is None:
        raise HTTPException(status_code=400, detail=f"Unknown task: {payload.task}")

    if task["needs_resume"]:
        workspace = local_agent_service.resolve_local_workspace(db)
        if workspace is None:
            raise HTTPException(status_code=400, detail="Upload a resume first so your assistant has something to match.")
        if not resume_consent.is_granted(workspace.id):
            raise HTTPException(
                status_code=409,
                detail="Turn on resume access first so your assistant can read your resume.",
            )

    try:
        outcome = agent_integration_service.run_headless(payload.client, str(task["prompt"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return AgentRunResponse(**outcome)


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
