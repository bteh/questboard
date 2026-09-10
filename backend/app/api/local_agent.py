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
    AgentProgressResponse,
    AgentProgressStep,
    AgentClientsResponse,
    AgentClientStatus,
    AgentConnectRequest,
    AgentConsentRequest,
    AgentConsentStatus,
    AgentIntentRequest,
    AgentIntentResponse,
    AgentRunRequest,
    AgentRunResponse,
    RoleProposalDecisionRequest,
    RoleProposalDecisionResponse,
    RoleProposalsResponse,
)
from app.services import (
    agent_integration_service,
    agent_run_progress,
    local_agent_service,
    resume_consent,
)

router = APIRouter(prefix="/agent", tags=["agent"])

# Server-owned task prompts. The client sends only a task id, so it can't inject
# an arbitrary prompt or widen the tool allow-list. Each entry says whether the
# task needs the resume (and therefore resume consent).
_AGENT_TASKS: dict[str, dict[str, object]] = {
    "propose_roles": {
        "needs_resume": True,
        "prompt": (
            "Use the Questboard MCP tools. First call read_resume_for_matching to read my "
            "resume, then get_career_preferences for my saved target roles and keywords. "
            "Then call propose_career_preferences ONCE with two lists. roles: 6 to 10 "
            "target roles I should search: keep the saved roles that fit my resume, add "
            "adjacent titles and variants I might not think to search for, and drop "
            "nothing I added myself. Calibrate to my resume's ACTUAL seniority: at most "
            "one level up from titles I have held. If my resume shows no professional "
            "title in the field I am aiming at, I am breaking in: propose entry-level and "
            "adjacent titles that hire people from my background, never senior, staff, "
            "lead, or manager titles. keywords: 10 to 15 search keywords, the tools, "
            "technologies, and domain terms from my resume that a posting for those roles "
            "would mention: keep the saved keywords that still fit, add what is missing, "
            "and drop nothing I added myself. Give a rationale of two or three plain "
            "sentences. Proposing records a suggestion for me to accept in the app; do "
            "NOT call set_career_preferences, refresh_work, or search_work, and do not "
            "save anything yourself. If the tool's answer carries a note, repeat it in "
            "one plain sentence. Stop after the proposal."
        ),
    },
    "find_and_rank": {
        "needs_resume": True,
        "prompt": (
            "Use the Questboard MCP tools. First call read_resume_for_matching to read my "
            "resume, then get_career_preferences for my saved target roles. Build "
            "judged_roles as EVERY saved role plus adjacent titles and variants I might not "
            "think to search for (related functions, level-appropriate alternates). You may "
            "only add, never remove: even a saved role that looks wrong for my resume gets "
            "searched, I chose it, so search it anyway this run. If you believe a role should "
            "be dropped or a better one added, call propose_career_preferences with the full "
            "list you'd suggest and why; that records a proposal for me to accept later, it "
            "does not change my saved search, and do NOT save anything yourself. Calibrate "
            "proposals to my resume's ACTUAL seniority: at most one level up from titles I "
            "have held, so a first-line manager gets Senior Manager suggestions, not VP or "
            "Head-of unless my resume already shows that level. And do not propose dropping "
            "a role I added myself; if I kept it after you suggested dropping it, that answer "
            "stands. Proposing is optional: skip it entirely when the saved list already "
            "covers the resume, and if the proposal comes back with a note saying I recently "
            "chose to keep my roles, give that one sentence at most and move on. "
            "Start the source pull with refresh_work(roles=judged_roles), EXACTLY ONCE for "
            "the whole run. Omitted refresh arguments inherit my saved keywords, places, "
            "remote stance, pay floor, freshness, strictness, and staffing-agency preference; "
            "never weaken those constraints. search_work enforces the same saved contract. "
            "Never start a second pull, and never use refresh_work to check "
            "on the first one, checking is get_refresh_status's job. Do NOT wait on the "
            "pull: it runs on its own and new rows land when it finishes. While it runs, "
            "call search_work(queries=judged_roles, page_size=50). It returns a compact, "
            "resumable shortlist across the eligible board, not merely the newest rows. A few "
            "current judgments are global rank anchors; the remaining slots advance through "
            "the best needs_review rows instead of returning the same reviewed page forever. "
            "Retrieval order "
            "is not a fit verdict, so map each candidate against my actual background. Every "
            "row has assistant_review.state: rows marked current are prior judgments to reuse "
            "as global rank anchors; spend model work ONLY on rows marked needs_review. Assign "
            "each non-skip a GLOBAL desired rank relative to the current anchors (a new #2 may "
            "shift the old #2 down automatically). If no row needs review, do not call "
            "set_work_fit. Otherwise call set_work_fit IN BATCHES of about 15, best candidates "
            "first, until every needs_review row in this shortlist has a verdict. Each batch "
            "lands on my board as soon as you send it, so if the run is cut short I keep "
            "what you already decided. Do NOT wait and send them all at the end. Then call "
            "search_work again: repeat the shortlist-and-batches sweep until needs_review_total "
            "is zero. If time runs out, stop honestly; the next run resumes with the next unseen "
            "rows because completed batches are durable. AFTER your last batch, check the pull "
            "once with get_refresh_status(run_id from "
            "refresh_work): if it finished, call search_work(queries=judged_roles, page_size=50) "
            "again and give verdicts only to needs_review rows that fresh arrivals introduced, "
            "again placing non-skips at their correct global rank; if it is still "
            "running, say in your summary that fresh arrivals are unranked until my next "
            "run, then stop. Verdict scale: "
            "strong / good / reach for ones worth my time, skip for ones that don't fit "
            "(wrong role, staffing agency, junk). Rank the non-skips 1..N best-first; skips "
            "need no rank. Keep it FAST: each 'why' is a short phrase (a few words, <=12), and "
            "add a 'caveat' only when there's a real risk (wrong level, comp floor, remote "
            "unclear). Each needs its opportunity_id. set_work_fit is what puts your verdicts "
            "on my board. After that, reply with just a one-line summary that also names any "
            "roles you proposed, not added (e.g. 'Proposed adding Analytics Engineering "
            "Manager; scored 28: 6 strong/good, rest reach or skip; GitLab EM is #1.'). Be "
            "honest; don't invent postings."
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

    # Drop the previous run's trail so a poll during THIS run can't read the
    # last one's steps and report progress that already happened.
    agent_run_progress.clear()
    agent_run_progress.mark_requested(payload.task)
    try:
        outcome = agent_integration_service.run_headless(payload.client, str(task["prompt"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return AgentRunResponse(**outcome)


@router.post("/intent", response_model=AgentIntentResponse)
def mark_agent_intent(payload: AgentIntentRequest) -> AgentIntentResponse:
    """Note that the person is about to run a task by hand.

    A pasted prompt in Claude Desktop or Codex never passes through /run, so
    this is how that run gets the same asked-for treatment: a proposal the
    person asked for answers even inside the quiet week after a "Not now".
    """
    _require_local()
    if payload.task not in _AGENT_TASKS:
        raise HTTPException(status_code=400, detail=f"Unknown task: {payload.task}")
    agent_run_progress.mark_requested(payload.task)
    return AgentIntentResponse(task=payload.task)


@router.get("/progress", response_model=AgentProgressResponse)
def get_agent_progress() -> AgentProgressResponse:
    """Where the running assistant has actually got to.

    The run is a separate process, so the board polls this instead of guessing
    from a stopwatch. Steps are the MCP tool calls the run has made.
    """
    _require_local()
    steps = agent_run_progress.read()["steps"]
    return AgentProgressResponse(
        steps=[AgentProgressStep(**s) for s in steps],
        phase=agent_run_progress.phase_label(steps),
    )


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


@router.get("/role-proposals", response_model=RoleProposalsResponse)
def get_role_proposals(db: Session = Depends(get_db)) -> RoleProposalsResponse:
    """Pending role proposals the connected assistant has recorded."""
    _require_local()
    return RoleProposalsResponse(
        **local_agent_service.list_role_proposals(db, status="pending")
    )


@router.post(
    "/role-proposals/{proposal_id}/decide", response_model=RoleProposalDecisionResponse
)
def decide_role_proposal(
    proposal_id: int,
    payload: RoleProposalDecisionRequest,
    db: Session = Depends(get_db),
) -> RoleProposalDecisionResponse:
    """Accept or reject a pending role proposal.

    Accepting patches only the saved roles, and refuses with a 409 if the
    saved roles changed since the proposal was made (the proposal's base
    went stale) rather than overwriting that change.
    """
    _require_local()
    try:
        result = local_agent_service.decide_role_proposal(
            db, proposal_id, accept=payload.accept
        )
    except local_agent_service.RoleProposalConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RoleProposalDecisionResponse(**result)
