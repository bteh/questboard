"""Local, model-free tools for Questboard's agent integrations.

The MCP adapter is intentionally thin.  This module owns the useful behavior
so it can be tested without starting an MCP transport and reused by another
local client later.  Nothing here constructs or calls an LLM.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.application import ApplicationRecord
from app.models.workspace import (
    AgentRoleProposal,
    Workspace,
    WorkspacePreferences,
    WorkspaceResume,
)
from app.services import (
    agent_run_progress,
    application_service,
    lane_cache,
    workspace_service,
)
from job_finder.job_trust import is_direct_source
from job_finder.kinds import get_kinds, kind_for_vertical, vertical_values_for
from job_finder.models.database import ScrapeRunRecord
from job_finder.tools.scrapers._utils import _strip_html

_WORK_KIND = "work"
# One cap for every list the assistant hands us: saved roles, proposals, and
# the pull. 15 blocked all additions once the saved list filled; 18 leaves
# room to propose while keeping the pull fan-out bounded.
ROLES_CAP = workspace_service.ROLES_CAP
_EXCERPT_CHARS = 1200
# A list row carries only enough body text to decide whether a posting is worth
# opening; `get_opportunity` serves the long excerpt for finalists. A full page
# of 1,200-char excerpts blew past the agent CLI's tool-result cap and cost a
# whole run (see tests/test_mcp_result_size.py).
_LIST_EXCERPT_CHARS = 260
_MAX_RESULTS = 50
# Agent CLIs reject an oversized tool result outright rather than truncating it.
# Claude Code's ceiling lands near 82k characters; hold a page well under that.
_MCP_RESULT_CHAR_BUDGET = 60_000
_ALLOWED_STATUSES = frozenset(
    {
        "found",
        "reviewed",
        "clipped",
        "applying",
        "applied",
        "interviewing",
        "offer",
        "rejected",
        "withdrawn",
        "shelved",
        "booked",
        "attended",
        "paid_out",
        "expired",
    }
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _json_list(value: str | None, *, limit: int = 10) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed[:limit] if isinstance(parsed, list) else []


def _json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _content_hash(record: ApplicationRecord) -> str:
    payload = "\n".join(
        str(value or "")
        for value in (
            record.job_title,
            record.company,
            record.location,
            record.description,
            record.date_posted,
            record.job_url,
            record.work_type,
            record.remote_scope,
            record.salary_min,
            record.salary_max,
            record.salary_min_annualized,
            record.salary_max_annualized,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fit_profile_hash(db: Session, workspace_id: str | None = None) -> str:
    """Fingerprint only the resume and preferences that can change a Work fit.

    Fit annotations use this together with the posting content hash. Keeping
    the fingerprint structural (rather than keying on ``updated_at``) means an
    unrelated settings save does not make every judgment stale.
    """

    profile = career_preferences(db, workspace_id)
    preferences = profile.get("preferences") or {}
    resume = profile.get("resume") or {}
    relevant = {
        "roles": preferences.get("roles") or [],
        "keywords": preferences.get("keywords") or [],
        "companies": preferences.get("companies") or [],
        "preferred_places": preferences.get("preferred_places") or [],
        "workplace_preference": preferences.get("workplace_preference") or "",
        "max_days_old": preferences.get("max_days_old"),
        "current_title": preferences.get("current_title") or "",
        "current_level": preferences.get("current_level") or "",
        "compensation": preferences.get("compensation") or {},
        "exclude_staffing_agencies": preferences.get("exclude_staffing_agencies"),
        "match_strictness": preferences.get("match_strictness") or "",
        "resume_sha256": resume.get("sha256") or "",
        "resume_updated_at": resume.get("updated_at") or "",
    }
    encoded = json.dumps(relevant, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parsed_fit(record: ApplicationRecord) -> dict[str, Any]:
    raw = record.agent_fit_json or ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def fit_review_state(record: ApplicationRecord, profile_hash: str) -> dict[str, Any]:
    """Whether a stored assistant verdict still describes this job/profile."""

    fit = _parsed_fit(record)
    if fit.get("verdict") not in _FIT_VERDICTS:
        return {"current": False, "reason": "not_reviewed", "fit": fit}
    if fit.get("profile_hash") != profile_hash:
        reason = "legacy_fit" if not fit.get("profile_hash") else "profile_changed"
        return {"current": False, "reason": reason, "fit": fit}
    if fit.get("content_hash") != _content_hash(record):
        return {"current": False, "reason": "posting_changed", "fit": fit}
    return {"current": True, "reason": "current", "fit": fit}


def _requested_workspace(db: Session, workspace_id: str | None = None) -> Workspace | None:
    if workspace_id:
        return db.get(Workspace, workspace_id)
    return None


def resolve_local_workspace(
    db: Session, workspace_id: str | None = None
) -> Workspace | None:
    """Choose the meaningful local workspace, not the newest empty session.

    Browser reloads can leave several anonymous local workspaces behind.  A
    parsed resume is the strongest ownership signal, then saved preferences,
    then recent activity.  This keeps MCP aligned with the profile the person
    actually configured in the app.
    """

    requested = _requested_workspace(db, workspace_id)
    if requested is not None:
        return requested

    resume_workspace = (
        db.query(Workspace)
        .join(WorkspaceResume, WorkspaceResume.workspace_id == Workspace.id)
        .filter(WorkspaceResume.extracted_text != "")
        .order_by(WorkspaceResume.updated_at.desc(), Workspace.last_active_at.desc())
        .first()
    )
    if resume_workspace is not None:
        return resume_workspace

    preference_workspace = (
        db.query(Workspace)
        .join(WorkspacePreferences, WorkspacePreferences.workspace_id == Workspace.id)
        .order_by(
            case(
                (WorkspacePreferences.roles_json.notin_(("", "[]")), 0),
                (WorkspacePreferences.keywords_json.notin_(("", "[]")), 1),
                else_=2,
            ),
            WorkspacePreferences.updated_at.desc(),
            Workspace.last_active_at.desc(),
        )
        .first()
    )
    if preference_workspace is not None:
        return preference_workspace

    return db.query(Workspace).order_by(Workspace.last_active_at.desc()).first()


def career_preferences(
    db: Session, workspace_id: str | None = None
) -> dict[str, Any]:
    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return {
            "configured": False,
            "workspace_id": None,
            "preferences": {},
            "resume": {"available": False},
        }

    preferences = workspace_service.get_workspace_preferences(db, workspace.id)
    resume = workspace_service.get_workspace_resume(db, workspace.id)
    return {
        "configured": True,
        "workspace_id": workspace.id,
        "preferences": preferences.model_dump(mode="json"),
        "resume": {
            "available": bool(resume and resume.extracted_text),
            "filename": resume.original_filename if resume else "",
            "parse_status": resume.parse_status if resume else "missing",
            "sha256": resume.file_sha256 if resume else "",
            "updated_at": _iso(resume.updated_at) if resume else None,
        },
        "raw_resume_returned": False,
    }


def set_career_preferences(
    db: Session,
    *,
    roles: list[str] | None = None,
    keywords: list[str] | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Save the user's target roles and keywords to the local workspace.

    This is the intent that decides which career candidates search_work
    retrieves, so a fresh resume with no roles set leaves the Find Work board
    starved. A connected agent can read the resume and propose these, or the
    person types them in Settings; either way this persists them locally.
    Only the two intent fields change; every other saved preference the person
    set (location, pay, filters) is preserved. Never performs an external
    action.
    """
    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        raise ValueError("No local workspace found to save preferences to.")
    if roles is None and keywords is None:
        raise ValueError("Provide roles and/or keywords to save.")

    current = workspace_service.get_workspace_preferences(db, workspace.id)
    new_roles = clean_terms(roles, limit=ROLES_CAP) if roles is not None else current.roles
    new_keywords = clean_terms(keywords, limit=20) if keywords is not None else current.keywords
    # Never let this tool blank out all retrieval intent. Empty or
    # whitespace-only lists clean to [], and saving both would starve Find
    # Work, the exact state this tool exists to prevent. A caller that means
    # to clear one field can still do so as long as the other stays set.
    if not new_roles and not new_keywords:
        raise ValueError(
            "Refusing to clear both roles and keywords: that leaves Find Work with "
            "no target. Provide at least one real role or keyword."
        )
    updated = current.model_copy(update={"roles": new_roles, "keywords": new_keywords})
    workspace_service.save_workspace_preferences(db, workspace.id, updated)

    result = career_preferences(db, workspace.id)
    result["saved"] = True
    result["external_action_performed"] = False
    return result


class RoleProposalConflict(ValueError):
    """Raised when a proposal's base roles no longer match the saved roles.

    Someone (or another accepted proposal) changed roles after this proposal
    was made, so accepting it now would blend a stale suggestion into the
    live save. The caller must reject it and ask for a fresh proposal.
    """


def _as_utc(value: datetime) -> datetime:
    """SQLite hands naive datetimes back; pin them UTC for arithmetic."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _clean_rationale(raw: str, limit: int = 500) -> str:
    """Whitespace-collapse and trim at a word boundary, never mid-letter.

    A hard [:500] slice shipped "as a common phrasi" to the board. The trim is
    reader-visible text, so it ends at a whole word with an ellipsis.
    """
    text = " ".join(str(raw).split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    at_space = cut.rsplit(" ", 1)[0].rstrip()
    return f"{at_space or cut}…"


def _proposal_payload(proposal: AgentRoleProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "workspace_id": proposal.workspace_id,
        "base_roles": _json_list(proposal.base_roles_json, limit=ROLES_CAP),
        "proposed_roles": _json_list(proposal.proposed_roles_json, limit=ROLES_CAP),
        "rationale": proposal.rationale or "",
        "status": proposal.status,
        "created_at": _iso(proposal.created_at),
        "decided_at": _iso(proposal.decided_at),
    }


def propose_career_preferences(
    db: Session,
    roles: list[str],
    rationale: str = "",
    *,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Record a pending role proposal; never writes workspace_preferences.

    Captures the currently saved roles as the proposal's base, so a later
    accept can detect drift. Any prior pending proposal for this workspace is
    marked superseded, since only the latest suggestion should be actionable.
    """
    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        raise ValueError("No local workspace found to record a proposal for.")
    cleaned_roles = clean_terms(roles, limit=ROLES_CAP)
    if not cleaned_roles:
        raise ValueError("Provide at least one role to propose.")
    # Refuse, never truncate: a 17-title proposal silently capped to 15
    # chopped off exactly the two additions being proposed, and the returned
    # payload matched the saved list, which read as corruption to the caller.
    submitted = len({str(r).strip().lower() for r in roles if str(r).strip()})
    if submitted > len(cleaned_roles):
        raise ValueError(
            f"You proposed {submitted} titles but the list caps at {ROLES_CAP}. "
            f"Resubmit at most {ROLES_CAP}, dropping something to make room."
        )

    current = workspace_service.get_workspace_preferences(db, workspace.id)

    now = datetime.now(timezone.utc)

    # The same list again is an answer the user already has, not a new
    # proposal. Every run used to supersede and recreate an identical row, so
    # the card nagged on every pull; and a list the user rejected in the last
    # week coming straight back turns "Keep mine" into a question that never
    # stays answered. Order matters: check pending first, so an identical
    # pending proposal is returned untouched rather than superseded.
    proposed_set = {r.lower() for r in cleaned_roles}
    recent = (
        db.query(AgentRoleProposal)
        .filter(
            AgentRoleProposal.workspace_id == workspace.id,
            AgentRoleProposal.status.in_(("pending", "rejected")),
        )
        .order_by(AgentRoleProposal.created_at.desc())
        .limit(20)
        .all()
    )
    for previous in recent:
        if {r.lower() for r in _json_list(previous.proposed_roles_json, limit=ROLES_CAP)} != proposed_set:
            continue
        if previous.status == "pending":
            payload = _proposal_payload(previous)
            payload["note"] = (
                "An identical proposal is already pending; returning it "
                "instead of creating a duplicate."
            )
            return payload
        if previous.decided_at and (now - _as_utc(previous.decided_at)).days < 7:
            payload = _proposal_payload(previous)
            payload["note"] = (
                "The user rejected this same list recently; that answer "
                "stands, so no new proposal was recorded."
            )
            return payload

    # "Keep mine" answers "should my roles change?", not one specific list.
    # The run after a rejection proposed a slightly different trio and the
    # card came straight back (Aug 2026), so a rejection quiets every
    # proposal for a week. Editing the saved roles reopens the door early:
    # the base captured at proposal time no longer matching the saved list
    # is the signal the user gave the assistant something new to react to.
    last_rejection = next((p for p in recent if p.status == "rejected"), None)
    if (
        last_rejection is not None
        and last_rejection.decided_at
        and (now - _as_utc(last_rejection.decided_at)).days < 7
        and {r.lower() for r in _json_list(last_rejection.base_roles_json, limit=ROLES_CAP)}
        == {r.lower() for r in current.roles}
    ):
        payload = _proposal_payload(last_rejection)
        payload["note"] = (
            "The user chose to keep their roles within the last week and has "
            "not changed them since, so no new proposal was recorded. Mention "
            "this in at most one sentence and move on."
        )
        return payload

    # A guarded UPDATE, not loaded objects: a row this session read as pending
    # may have been accepted by the user mid-run, and writing "superseded"
    # over "accepted" by primary key would erase their decision.
    db.query(AgentRoleProposal).filter(
        AgentRoleProposal.workspace_id == workspace.id,
        AgentRoleProposal.status == "pending",
    ).update(
        {AgentRoleProposal.status: "superseded", AgentRoleProposal.decided_at: now},
        synchronize_session=False,
    )

    proposal = AgentRoleProposal(
        workspace_id=workspace.id,
        base_roles_json=json.dumps(current.roles),
        proposed_roles_json=json.dumps(cleaned_roles),
        rationale=_clean_rationale(rationale),
        status="pending",
        created_at=now,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return _proposal_payload(proposal)


def list_role_proposals(
    db: Session, status: str = "pending", *, workspace_id: str | None = None
) -> dict[str, Any]:
    """List role proposals for the local workspace, newest first."""
    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return {"proposals": []}

    query = db.query(AgentRoleProposal).filter(
        AgentRoleProposal.workspace_id == workspace.id
    )
    if status:
        query = query.filter(AgentRoleProposal.status == status)
    proposals = query.order_by(AgentRoleProposal.created_at.desc()).all()
    return {"proposals": [_proposal_payload(p) for p in proposals]}


def decide_role_proposal(
    db: Session, proposal_id: int, accept: bool
) -> dict[str, Any]:
    """Accept or reject a pending role proposal.

    Rejecting only marks the row rejected. Accepting re-reads the currently
    saved preferences and patches ONLY roles through save_workspace_preferences
    (a read-modify-write, same as set_career_preferences), but first checks
    that the current roles still match the proposal's base_roles_json; a
    mismatch means the base went stale and raises RoleProposalConflict
    instead of writing anything.
    """
    proposal = db.get(AgentRoleProposal, proposal_id)
    if proposal is None:
        raise ValueError(f"No role proposal found with id {proposal_id}.")
    if proposal.status != "pending":
        raise ValueError(f"Proposal {proposal_id} is already {proposal.status}.")

    now = datetime.now(timezone.utc)
    if not accept:
        proposal.status = "rejected"
        proposal.decided_at = now
        db.commit()
        return _proposal_payload(proposal)

    current = workspace_service.get_workspace_preferences(db, proposal.workspace_id)
    base_roles = _json_list(proposal.base_roles_json, limit=ROLES_CAP)
    if current.roles != base_roles:
        raise RoleProposalConflict(
            "Your saved roles changed since this proposal was made; accepting it "
            "now would overwrite that change. Reject it and ask for a fresh "
            "proposal instead."
        )

    # Claim the row first with a guarded UPDATE. The status read above came
    # from the identity map and can be stale: a run may have superseded this
    # proposal between that read and now, and an unguarded accept would write
    # "accepted" over the newer run's verdict, then save roles a fresher
    # proposal already replaced. Zero rows claimed means someone else decided
    # first; their decision wins.
    claimed = (
        db.query(AgentRoleProposal)
        .filter(
            AgentRoleProposal.id == proposal.id,
            AgentRoleProposal.status == "pending",
        )
        .update(
            {AgentRoleProposal.status: "accepted", AgentRoleProposal.decided_at: now},
            synchronize_session=False,
        )
    )
    if not claimed:
        db.rollback()
        raise RoleProposalConflict(
            "This proposal was superseded while you decided; a newer suggestion "
            "exists. Review the latest one instead."
        )

    try:
        proposed_roles = _json_list(proposal.proposed_roles_json, limit=ROLES_CAP)
        updated = current.model_copy(update={"roles": proposed_roles})
        workspace_service.save_workspace_preferences(
            db, proposal.workspace_id, updated, commit=False
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(proposal)

    result = _proposal_payload(proposal)
    result["external_action_performed"] = False
    return result


def resume_for_matching(
    db: Session, workspace_id: str | None = None
) -> dict[str, Any]:
    """Return the local resume only for an explicitly requested agent match."""

    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return {"available": False, "resume_text": "", "reason": "No local profile"}
    # The resume is PII. Return it only when a PERSON has granted consent from
    # the Questboard app / CLI; no MCP tool can grant it. This makes the
    # "only after explicit permission" promise real in code, not just in the
    # agent instructions (which a prompt-injected source description could
    # ignore).
    from app.services import resume_consent

    if not resume_consent.is_granted(workspace.id):
        return {
            "available": False,
            "resume_text": "",
            "reason": (
                "Resume access is not authorized. A person must grant it in "
                "Questboard (Settings, or `make agent-consent-grant`); the "
                "connected agent cannot grant it itself."
            ),
            "consent_required": True,
        }
    resume = workspace_service.get_workspace_resume(db, workspace.id)
    if resume is None or not resume.extracted_text:
        return {
            "available": False,
            "resume_text": "",
            "reason": "No parsed resume is stored in this Questboard workspace",
        }
    return {
        "available": True,
        "filename": resume.original_filename,
        "sha256": resume.file_sha256,
        "updated_at": _iso(resume.updated_at),
        "resume_text": resume.extracted_text,
        "privacy_notice": (
            "This text came from the user's local Questboard data. The connected "
            "agent provider may receive it as tool context; Questboard does not."
        ),
    }


def _saved_search_defaults(
    db: Session, workspace_id: str | None = None
) -> tuple[list[str], str, str, int, float | None, float]:
    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return [], "", "remote_friendly", 14, None, 1.0
    preferences = workspace_service.get_workspace_preferences(db, workspace.id)
    place = next(
        (
            item.label
            for item in preferences.preferred_places
            if item.label.strip().lower() not in {"remote", "anywhere"}
        ),
        "",
    )
    if not place:
        # Local browser sessions historically created duplicate workspaces.
        # If the current one says only "Remote" (no country), recover the
        # last concrete jurisdiction saved alongside the exact same resume.
        current_resume = (
            db.query(WorkspaceResume)
            .filter(WorkspaceResume.workspace_id == workspace.id)
            .first()
        )
        if current_resume and current_resume.file_sha256:
            sibling_ids = [
                row.workspace_id
                for row in db.query(WorkspaceResume)
                .filter(
                    WorkspaceResume.file_sha256 == current_resume.file_sha256,
                    WorkspaceResume.workspace_id != workspace.id,
                )
                .order_by(WorkspaceResume.updated_at.desc())
                .all()
            ]
            for sibling_id in sibling_ids:
                sibling = workspace_service.get_workspace_preferences(db, sibling_id)
                place = next(
                    (
                        item.label
                        for item in sibling.preferred_places
                        if item.label.strip().lower() not in {"remote", "anywhere"}
                        and (item.country_code or item.country or item.city or item.region)
                    ),
                    "",
                )
                if place:
                    break
    floor = preferences.compensation.min_acceptable_tc or preferences.compensation.min_base
    # Saved minimum means minimum. Role-match strictness may change recall,
    # but it must not lower this number behind the user's back.
    salary_flex = 1.0
    role_queries = list(preferences.roles)
    if not role_queries and preferences.current_title:
        role_queries.append(preferences.current_title)
    return (
        role_queries,
        place,
        preferences.workplace_preference,
        preferences.max_days_old,
        floor,
        salary_flex,
    )


def _clean_excerpt(text: str | None, limit: int = _EXCERPT_CHARS) -> str:
    """Serve a clean excerpt: strip residual HTML/entities (some stored
    descriptions predate the scraper-side fix) and truncate on a word
    boundary with an ellipsis instead of cutting mid-word."""
    cleaned = _strip_html(text or "")
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.rstrip() + "…"


def _candidate_payload(record: ApplicationRecord, *, detail: bool = False) -> dict[str, Any]:
    kind = kind_for_vertical(record.vertical or "career")
    payload: dict[str, Any] = {
        "opportunity_id": record.id,
        "kind": kind.id if kind else record.vertical,
        "title": record.job_title,
        "organization": record.company,
        "location": record.location or "Unknown",
        "work_type": record.work_type or ("remote" if record.is_remote else "unknown"),
        "remote_scope": record.remote_scope or "unknown",
        "pay": {
            "minimum": record.salary_min,
            "maximum": record.salary_max,
            "currency": record.salary_currency or None,
            "period": record.salary_period or None,
            "source": record.salary_source or "unknown",
        },
        "freshness": {
            "source_posted_at": record.date_posted or None,
            "source_date_confidence": record.date_confidence or "missing",
            "questboard_first_seen_at": _iso(record.date_found),
            "source_last_seen_at": _iso(record.last_seen_at),
            "url_status": record.url_status or "unknown",
        },
        "source": {
            "name": record.source or "Unknown",
            "url": record.job_url or "",
            "direct": is_direct_source(record.source or ""),
        },
        "retrieval": {
            # NULL columns mean the hybrid-ranking step never ran for this
            # row — say so, instead of the ambiguous 'unclassified'.
            "bucket": record.match_bucket or "not_ranked",
            "method": record.rank_source or "not_ranked",
            "reasons": _json_list(record.match_reasons_json, limit=3),
            "is_fit_assessment": False,
        },
        "status": record.status or "found",
        "description_excerpt": _clean_excerpt(
            record.description,
            _EXCERPT_CHARS if detail else _LIST_EXCERPT_CHARS,
        ),
    }
    if detail:
        payload.update(
            {
                "description": record.description or "",
                "description_is_untrusted_source_content": True,
                "content_hash": _content_hash(record),
                # A legacy keyword-scorer artifact, NOT a computed resume-fit
                # verdict. Named so the agent can't mistake it for one.
                "legacy_keyword_score_evidence": record.score_evidence,
                "quest_details": _json_object(record.quest_json),
                "event_start": _iso(record.event_start),
                "event_end": _iso(record.event_end),
                "is_rolling": bool(record.is_rolling),
                "first_quest_ok": bool(record.first_quest_ok),
            }
        )
    return payload


def clean_terms(values: list[str] | None, *, limit: int = 12) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = " ".join(str(value).split())[:120]
        lowered = item.lower()
        if not item or lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


_ROLE_TOKEN_ALIASES = {
    "architectural": "architect",
    "engineering": "engineer",
    "centers": "center",
    "centres": "centre",
    "mgr": "manager",
    "operations": "ops",
    "products": "product",
    "programs": "program",
    "projects": "project",
    "scientist": "science",
    "scientists": "science",
    "stewardship": "steward",
    "sr": "senior",
}
_ROLE_FILLER_TOKENS = frozenset({"a", "an", "and", "of", "the"})
_OCCUPATION_CONFLICT_TOKENS = frozenset(
    {"center", "centre", "clinical", "product", "program", "project", "science"}
)
# "Data Center/Centre" poisons the word "data" itself (facilities work), so
# these conflict anywhere in the title. The other occupation words only
# conflict in a segment that names the role: as an org qualifier
# ("..., Personalization - Central Product Insights", "- DoD Program") they
# describe the team, not the person.
_GLOBAL_CONFLICT_TOKENS = frozenset({"center", "centre"})

_TITLE_SEGMENT_SPLIT = re.compile(r"[,:|()/]|\s[-–—]\s")


def _conflict_scope_tokens(title: str | None) -> set[str]:
    """Tokens allowed to carry an occupation conflict: the first segment (the
    role itself) plus any later segment that names a role of its own
    ("Data Platform - Senior Product Manager")."""
    segments = [
        seg for seg in (s.strip() for s in _TITLE_SEGMENT_SPLIT.split(str(title or ""))) if seg
    ]
    if not segments:
        return set()
    segment_tokens = [_role_tokens(seg) for seg in segments]
    scope = set(segment_tokens[0])
    rest = segment_tokens[1:]
    if rest and not (scope - _ROLE_GENERIC_TOKENS):
        # "Senior Manager, Clinical Engineering": a generic-only first segment
        # means the next segment names the discipline, so its words are the
        # role's own, not a team qualifier.
        scope |= rest[0]
        rest = rest[1:]
    for tokens in rest:
        if tokens & _ROLE_GENERIC_TOKENS:
            scope |= tokens
    return scope


def _role_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+", str(value or "").lower()):
        if raw in _ROLE_FILLER_TOKENS:
            continue
        tokens.add(_ROLE_TOKEN_ALIASES.get(raw, raw))
    return tokens


# Seniority / scaffolding words that carry no domain signal on their own. A
# title that only shares one of these with a target role is not "in lane".
_ROLE_GENERIC_TOKENS = frozenset({
    "senior", "staff", "principal", "lead", "manager", "director", "head",
    "vp", "chief", "officer", "junior", "associate", "i", "ii", "iii", "iv",
})
# Pure seniority-LEVEL words (not role-type). Dropped from a role's retrieval
# tokens so the DOMAIN drives the match: "Staff Data Engineer" also finds
# "Senior Data Engineer" and "Data Engineer". Role-type words (manager,
# director, lead, head, engineer, analyst...) are intentionally NOT here.
_LEVEL_TOKENS = frozenset({
    "senior", "staff", "principal", "junior", "associate", "entry",
    "i", "ii", "iii", "iv", "v",
})


def _title_is_in_lane(title: str | None, queries: list[str]) -> bool:
    """Keep a candidate title that is a full role match (primary) OR shares a
    real domain word with a target role (adjacent).

    Retrieval is recall-first: the connected agent owns the fit verdict, so we
    hand it in-lane roles it can rank or skip rather than dropping them here.
    We still exclude titles with an occupation conflict the query doesn't share
    (a nurse/clinical/product role for an engineer), and titles that overlap
    only on a bare seniority word ("Manager" alone is not a data match).
    """

    title_tokens = _role_tokens(title)
    if not title_tokens:
        return False
    title_conflicts = (title_tokens & _GLOBAL_CONFLICT_TOKENS) | (
        _conflict_scope_tokens(title) & _OCCUPATION_CONFLICT_TOKENS
    )
    for query in queries:
        query_tokens = _role_tokens(query)
        if not query_tokens:
            continue
        query_conflicts = query_tokens & _OCCUPATION_CONFLICT_TOKENS
        if title_conflicts - query_conflicts:
            continue
        # primary: the whole role family is present
        if query_tokens.issubset(title_tokens):
            return True
        # adjacent: shares a domain (non-seniority) word with the target role
        domain = query_tokens - _ROLE_GENERIC_TOKENS
        if domain & title_tokens:
            return True
    return False


def local_relevance(record: ApplicationRecord, skill_terms: list[str]) -> dict[str, Any] | None:
    """A fast, offline skill-coverage signal for one job: which of the user's
    saved skills the posting actually names.

    This is NOT a fit verdict (that's the connected agent's job). It is a
    keyword-overlap hint so every row shows something instantly, without waiting
    on an LLM. Returns None when there are no skills to match on.
    """
    terms = [t for t in (skill_terms or []) if t and len(t) >= 2]
    if not terms:
        return None
    description = record.description or ""
    # Judge skills only when there's a real description to read; a title alone
    # can't tell us "weak", it just means we haven't seen the requirements.
    if len(description) < 120:
        return None
    text = f"{record.job_title or ''} {description}".lower()
    matched: list[str] = []
    seen: set[str] = set()
    for term in terms:
        low = term.lower()
        if low in seen:
            continue
        seen.add(low)
        if low in text:
            matched.append(term)
    count = len(matched)
    coverage = count / max(1, len(seen))
    if count >= 5 or coverage >= 0.4:
        band = "close"
    elif count >= 2 or coverage >= 0.2:
        band = "partial"
    else:
        band = "weak"
    return {"band": band, "skill_count": count, "matched_skills": matched[:8]}


def _annual_pay(record: ApplicationRecord) -> tuple[float | None, float | None]:
    return (
        record.salary_min_annualized
        if record.salary_min_annualized is not None
        else record.salary_min,
        record.salary_max_annualized
        if record.salary_max_annualized is not None
        else record.salary_max,
    )


def _work_retrieval_priority(
    record: ApplicationRecord,
    *,
    roles: list[str],
    skill_terms: list[str],
    target_companies: list[str],
    compensation_floor: float | None,
    compensation_currency: str | None = None,
) -> tuple[tuple[Any, ...], int | None, bool]:
    """Auditable, model-free priority for the assistant's compact shortlist.

    The old order was newest-only, so a weak new title evicted an exact saved
    role before the assistant could judge either. This key keeps role/title
    intent first and freshness as a tie-breaker; it is retrieval, never fit.
    """

    title_tokens = _role_tokens(record.job_title)
    best: tuple[int, int, float, int] = (0, 0, 0.0, -len(roles))
    best_role_index: int | None = None
    exact_role = False
    for index, role in enumerate(roles):
        role_tokens = _role_tokens(role)
        if not role_tokens:
            continue
        exact = int(role_tokens.issubset(title_tokens))
        role_levels = role_tokens & _ROLE_GENERIC_TOKENS
        same_level = int(bool(role_levels and role_levels & title_tokens))
        overlap = len(role_tokens & title_tokens) / max(1, len(role_tokens))
        candidate = (exact, same_level, overlap, -index)
        if candidate > best:
            best = candidate
            best_role_index = index
            exact_role = bool(exact)

    normalized_company = " ".join((record.company or "").casefold().split())
    target_company = int(bool(normalized_company) and any(
        company.casefold().strip() in normalized_company
        or normalized_company in company.casefold().strip()
        for company in target_companies
        if company.strip()
    ))
    pay_min, pay_max = _annual_pay(record)
    listing_currency = (record.salary_currency or "").strip().upper()
    target_currency = (compensation_currency or "").strip().upper()
    currencies_comparable = not target_currency or (
        bool(listing_currency) and listing_currency == target_currency
    )
    if compensation_floor is None or compensation_floor <= 0:
        pay_band = 1
    elif not currencies_comparable:
        pay_band = 1  # missing/unlike currency is unknown, never assumed USD
    elif pay_min is None and pay_max is None:
        pay_band = 1  # unknown stays eligible, but stated-above-floor wins
    elif max(value for value in (pay_min, pay_max) if value is not None) >= compensation_floor:
        pay_band = 2
    else:
        pay_band = 0
    relevance = local_relevance(record, skill_terms)
    skill_count = int((relevance or {}).get("skill_count") or 0)
    age_days = _source_age_days(record.date_posted, record.date_found)
    freshness = -age_days if age_days is not None else -10_000.0
    found_at = record.date_found
    if found_at is None:
        found = float("-inf")
    else:
        if found_at.tzinfo is None:
            found_at = found_at.replace(tzinfo=timezone.utc)
        found = found_at.timestamp()
    priority = (
        best[0],                 # exact saved-role token set
        best[1],                 # same seniority/role-type signal
        target_company,          # company the user explicitly watches
        pay_band,                # stated pay clears the saved floor
        skill_count,             # posting names saved stack terms
        best[2],                 # title-token coverage
        int(is_direct_source(record.source or "")),
        freshness,
        found,
    )
    return priority, best_role_index, exact_role


def _select_work_shortlist(
    records: list[ApplicationRecord],
    *,
    roles: list[str],
    skill_terms: list[str],
    target_companies: list[str],
    compensation_floor: float | None,
    compensation_currency: str | None = None,
    limit: int,
) -> list[ApplicationRecord]:
    """Select the best compact page while guaranteeing saved-role coverage."""

    scored = [
        (
            record,
            *_work_retrieval_priority(
                record,
                roles=roles,
                skill_terms=skill_terms,
                target_companies=target_companies,
                compensation_floor=compensation_floor,
                compensation_currency=compensation_currency,
            ),
        )
        for record in records
    ]
    scored.sort(key=lambda item: item[1], reverse=True)

    selected_ids: set[int] = set()
    # One exact title for each saved role prevents common broad families from
    # consuming all 50 slots. A row may cover only one quota even if two saved
    # titles normalize to the same token set; the global fill handles the rest.
    for role_index in range(len(roles)):
        for record, _priority, matched_role, exact in scored:
            if exact and matched_role == role_index and record.id not in selected_ids:
                selected_ids.add(record.id)
                break
        if len(selected_ids) >= limit:
            break

    for record, _priority, _matched_role, _exact in scored:
        if len(selected_ids) >= limit:
            break
        selected_ids.add(record.id)

    # Keep the delivered page in priority order, not quota-collection order.
    return [record for record, *_ in scored if record.id in selected_ids][:limit]


def _dedupe_work_key(record: ApplicationRecord) -> tuple[str, tuple[str, ...]]:
    company_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", (record.company or "").lower())
        if token not in {"co", "company", "corp", "corporation", "inc", "llc", "ltd"}
    ]
    title_tokens = _role_tokens(record.job_title)
    title_tokens.difference_update({"hybrid", "remote", "us", "usa"})
    return "".join(company_tokens), tuple(sorted(title_tokens))


def _dedupe_work_priority(record: ApplicationRecord) -> tuple[Any, ...]:
    age_days = _source_age_days(record.date_posted, record.date_found)
    found = record.date_found or datetime.min
    return (
        age_days is not None,
        -int(age_days) if age_days is not None else float("-inf"),
        is_direct_source(record.source or ""),
        bool(record.description),
        found,
    )


def _anchor_age_days(anchor: datetime | str | None) -> float | None:
    """Age of an anchor timestamp in days, or None when it can't be read.

    Accepts the ORM's datetime (naive means UTC, how SQLite hands
    ``date_found`` back) or a stored ISO string.
    """
    if isinstance(anchor, str):
        try:
            anchor = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(anchor, datetime):
        return None
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - anchor.astimezone(timezone.utc)
    return max(0.0, elapsed.total_seconds() / 86_400)


def _source_age_days(
    value: str | None, anchor: datetime | str | None = None
) -> float | None:
    """Normalize exact and human-readable source dates into an age in days.

    Relative prose ("Reposted 3 Days Ago", "Yesterday") only means something
    relative to the moment the source said it, which is when WE scraped the
    row. ``anchor`` is that moment (the record's date_found): with it, age =
    age(anchor) + the stated offset, so a row scraped six days ago saying
    "3 Days Ago" reads ~9 days old instead of eternally 3. Without an anchor
    the prose is unknowable and returns None. Absolute values (ISO, epoch)
    carry their own instant and ignore the anchor.
    """

    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    lowered = normalized.lower()
    offset_days: float | None = None
    if re.fullmatch(r"(?:re)?posted\s+today|today", lowered):
        offset_days = 0.0
    elif re.fullmatch(r"(?:re)?posted\s+yesterday|yesterday", lowered):
        offset_days = 1.0
    else:
        relative = re.fullmatch(
            r"(?:(?:re)?posted\s+)?(\d+)\s+"
            r"(minute|minutes|hour|hours|day|days)\s+ago",
            lowered,
        )
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2)
            if unit.startswith("minute"):
                offset_days = amount / (24 * 60)
            elif unit.startswith("hour"):
                offset_days = amount / 24
            else:
                offset_days = float(amount)
    if offset_days is not None:
        anchor_age = _anchor_age_days(anchor)
        if anchor_age is None:
            return None
        return anchor_age + offset_days

    # Only the two real epoch widths: 10 digits is seconds, 13 is
    # milliseconds. An 11 or 12 digit value is malformed; guessing its unit
    # lands it far in the future and clamps to age 0 (reads as posted today),
    # so leave it unknown instead.
    if re.fullmatch(r"\d{10}|\d{13}", normalized):
        timestamp = int(normalized)
        if len(normalized) == 13:
            timestamp /= 1000
        try:
            posted = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        elapsed = datetime.now(timezone.utc) - posted
        return max(0.0, elapsed.total_seconds() / 86_400)

    try:
        posted = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - posted.astimezone(timezone.utc)
    return max(0.0, elapsed.total_seconds() / 86_400)


def search_work(
    db: Session,
    *,
    queries: list[str] | None = None,
    location: str = "",
    workplace_preference: str = "saved",
    compensation_floor: float | None = None,
    compensation_currency: str | None = None,
    founding_only: bool = False,
    posted_within_days: int | None = None,
    found_within_days: int | None = None,
    timezone_name: str = "UTC",
    page_size: int = 20,
    use_saved_preferences: bool = True,
    workspace_id: str | None = None,
    result_limit: int | None = None,
    browse_all: bool = False,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = dict(
        queries=queries,
        location=location,
        workplace_preference=workplace_preference,
        compensation_floor=compensation_floor,
        compensation_currency=compensation_currency,
        founding_only=founding_only,
        posted_within_days=posted_within_days,
        found_within_days=found_within_days,
        timezone_name=timezone_name,
        page_size=page_size,
        use_saved_preferences=use_saved_preferences,
        workspace_id=workspace_id,
        result_limit=result_limit,
        browse_all=browse_all,
    )
    if not browse_all:
        return _search_work_uncached(db, **kwargs)
    # The human board's lane build walks every candidate through both title
    # gates for every saved role (~1s); the compact MCP path stays uncached
    # because agent runs are minute-scale anyway. lane_cache owns the
    # accuracy contract: any commit from any process invalidates.
    key = (
        "browse_all",
        fit_profile_hash(db, workspace_id),
        tuple(queries or ()),
        location,
        workplace_preference,
        compensation_floor,
        compensation_currency,
        founding_only,
        posted_within_days,
        found_within_days,
        timezone_name,
        page_size,
        use_saved_preferences,
        workspace_id,
        result_limit,
    )
    return lane_cache.get_or_build(
        db, key, lambda: _search_work_uncached(db, **kwargs)
    )


def _search_work_uncached(
    db: Session,
    *,
    queries: list[str] | None = None,
    location: str = "",
    workplace_preference: str = "saved",
    compensation_floor: float | None = None,
    compensation_currency: str | None = None,
    founding_only: bool = False,
    posted_within_days: int | None = None,
    # Arrived-in-the-last-N-days by the board's own date_found stamp; unlike
    # the posted window it can never hide a row for lacking a source date.
    found_within_days: int | None = None,
    timezone_name: str = "UTC",
    page_size: int = 20,
    use_saved_preferences: bool = True,
    workspace_id: str | None = None,
    result_limit: int | None = None,
    browse_all: bool = False,
) -> dict[str, Any]:
    # The MCP path stays compact. The human board opts into browse_all so its
    # total and pagination describe every eligible row rather than a shortlist.
    (
        saved_terms,
        saved_location,
        saved_workplace,
        saved_days,
        saved_floor,
        saved_salary_flex,
    ) = (
        _saved_search_defaults(db, workspace_id)
    )
    profile = career_preferences(db, workspace_id)
    preferences = (profile.get("preferences") or {}) if use_saved_preferences else {}
    saved_compensation = preferences.get("compensation") or {}
    skill_terms = clean_terms(preferences.get("keywords"), limit=ROLES_CAP)
    target_companies = clean_terms(preferences.get("companies"), limit=ROLES_CAP)
    match_strictness = str(preferences.get("match_strictness") or "balanced")
    exclude_staffing_agencies = bool(
        use_saved_preferences and preferences.get("exclude_staffing_agencies", True)
    )
    from job_finder.pipeline import _filter_jobs_by_level, _resolve_filter_settings
    from job_finder.tools.scrapers._utils import job_passes_role_filter

    filter_settings = _resolve_filter_settings({
        "filters": {"strictness": match_strictness},
    })
    profile_hash = fit_profile_hash(db, workspace_id)
    terms = clean_terms(queries, limit=ROLES_CAP)
    if not terms and use_saved_preferences:
        terms = clean_terms(saved_terms, limit=ROLES_CAP)
    effective_location = " ".join(location.split())[:120] or (
        saved_location if use_saved_preferences else ""
    )
    effective_workplace = (
        saved_workplace if workplace_preference == "saved" else workplace_preference
    )
    if effective_workplace not in {"remote_friendly", "remote_only", "location_only"}:
        raise ValueError("workplace_preference must be saved, remote_friendly, remote_only, or location_only")
    requested_floor = compensation_floor
    effective_floor = compensation_floor
    effective_currency = (compensation_currency or "").strip().upper()
    if not effective_currency and use_saved_preferences:
        effective_currency = str(saved_compensation.get("currency") or "").strip().upper()
    salary_flex = 1.0
    if effective_floor is None and use_saved_preferences:
        requested_floor = saved_floor
        salary_flex = saved_salary_flex
        effective_floor = saved_floor
    if posted_within_days is not None:
        posted_within_days = max(1, min(int(posted_within_days), 365))
    effective_freshness_window = posted_within_days
    if effective_freshness_window is None and use_saved_preferences:
        effective_freshness_window = max(1, min(int(saved_days), 365))
    effective_cap = max(1, int(result_limit)) if result_limit else _MAX_RESULTS
    page_size = max(1, min(int(page_size), effective_cap))
    candidate_page_size = 1000 if browse_all else min(1000, max(page_size * 10, 200))

    # Saved role families are token groups, not exact phrases. This retrieves
    # "Manager, Data Engineering" for "Data Engineering Manager" while the
    # Python check below prevents description-only and substring false hits.
    # Retrieval is recall-first: match a role on its DOMAIN words and drop the
    # pure seniority level, so "Staff Data Engineer" also surfaces "Senior Data
    # Engineer" and plain "Data Engineer" (the agent ranks; we don't pre-drop).
    role_groups = [
        [tok for tok in sorted(_role_tokens(term)) if tok not in _LEVEL_TOKENS]
        for term in terms
    ]
    role_groups = [group for group in role_groups if group]
    candidate_query = dict(
        title_token_groups=role_groups or None,
        is_remote=True if effective_workplace == "remote_only" else None,
        # Apply this before the bounded retrieval/shortlist. Filtering the
        # final 300 rows instead made a real founding role disappear whenever
        # ordinary exact-title matches consumed every shortlist slot.
        founding_only=founding_only,
        exclude_staffing_agencies=exclude_staffing_agencies,
        location=effective_location or None,
        location_strict=bool(
            effective_location and effective_workplace == "location_only"
        ),
        salary_min=effective_floor,
        salary_currency=effective_currency or None,
        exclude_dead=True,
        # Source dates are a mixture of ISO timestamps and labels such as
        # "Reposted 8 Days Ago". Filter them consistently after retrieval.
        posted_within_days=None,
        sort_by="date_found",
        sort_dir="desc",
        page=1,
        page_size=candidate_page_size,
        verticals=["career", "work"],
    )
    rows, candidate_total = application_service.get_applications(db, **candidate_query)
    if browse_all and candidate_total > len(rows):
        # The old 1,000-row prefilter ceiling made the later Python title,
        # freshness, and dedupe pass incapable of seeing the tail. Fetch the
        # exact SQL total for the human board; the MCP shortlist stays bounded.
        candidate_query["page_size"] = candidate_total
        rows, _ = application_service.get_applications(db, **candidate_query)

    stale_excluded = 0
    unknown_freshness_excluded = 0
    title_mismatch_excluded = 0
    level_mismatch_excluded = 0
    duplicate_records_excluded = 0

    # Apply title + freshness BEFORE dedup. Deduping first let a stale-known
    # record win its key and then get freshness-excluded, silently evicting a
    # still-live unknown-date duplicate that shared the key.
    found_bounds = None
    found_now = None
    if isinstance(found_within_days, int):
        found_now = datetime.now(timezone.utc)
        found_bounds = application_service.local_calendar_window_utc(
            max(1, min(found_within_days, 365)),
            timezone_name,
            now=found_now,
        )

    survivors: list[ApplicationRecord] = []
    intent_text = " ".join(terms + skill_terms).casefold()
    wants_founding = founding_only or any(
        term in intent_text
        for term in ("founding", "startup", "early-stage", "early stage", "first hire")
    )
    wants_crypto = any(
        term in intent_text
        for term in ("crypto", "web3", "blockchain", "defi", "solidity", "ethereum")
    )
    include_founding = bool(filter_settings.get("include_founding_titles", True)) and wants_founding
    match_mode = str(filter_settings.get("role_match_mode", "all_significant"))
    strictness = str(filter_settings.get("strictness", "balanced"))
    career_baseline = {
        "current_title": preferences.get("current_title") or "",
        "current_level": preferences.get("current_level") or "",
    }
    for row in rows:
        filter_job = {
            "title": row.job_title or "",
            "company": row.company or "",
            "source": row.source or "",
            "is_remote": bool(row.is_remote),
            "industry_tags": getattr(row, "industry_tags", "[]") or "[]",
        }
        primary_role_match = job_passes_role_filter(
            filter_job,
            terms,
            match_mode=match_mode,
            include_founding=include_founding,
            strictness=strictness,
            allow_crypto_rescue=False,
        )
        crypto_role_match = wants_crypto and job_passes_role_filter(
            filter_job,
            terms,
            match_mode=match_mode,
            include_founding=include_founding,
            strictness=strictness,
            allow_crypto_rescue=True,
        )
        # Two independent gates are deliberate. job_passes_role_filter mirrors
        # the pull's loose/balanced/strict vocabulary; _title_is_in_lane keeps
        # profession conflicts out (Product Manager, AI Platform and Data
        # Center Engineer must not become data-engineering matches merely by
        # sharing "platform" or "data").
        if terms and (
            not _title_is_in_lane(row.job_title, terms)
            or not (primary_role_match or crypto_role_match)
        ):
            title_mismatch_excluded += 1
            continue
        if not _filter_jobs_by_level(
            [filter_job],
            career_baseline,
            filters=filter_settings,
            target_roles=terms,
        ):
            level_mismatch_excluded += 1
            continue
        if found_bounds is not None:
            # Same first-seen calendar rule as board_filter_conditions. A
            # recent source date cannot resurrect an older board row; a
            # verifiably old source date can still prove today's arrival stale.
            found_start, found_end = found_bounds
            today_start, _ = application_service.local_calendar_window_utc(
                1,
                timezone_name,
                now=found_now,
            )
            posted_at = None
            posted_raw = (row.date_posted or "")[:19]
            if posted_raw.startswith("2"):
                try:
                    posted_at = datetime.fromisoformat(posted_raw)
                except ValueError:
                    posted_at = None
            arrived = (
                row.date_found is not None
                and found_start <= row.date_found < found_end
                and row.date_found <= found_now.replace(tzinfo=None)
            )
            provably_stale = (
                posted_at is not None
                and posted_at < today_start - timedelta(days=7)
                and (row.date_confidence or "").lower() != "missing"
            )
            if not (arrived and not provably_stale):
                continue
        age_days = _source_age_days(row.date_posted, row.date_found)
        if effective_freshness_window is not None and age_days is not None:
            if age_days > effective_freshness_window:
                stale_excluded += 1
                continue
        elif posted_within_days is not None or filter_settings.get("drop_missing_dates", False):
            # An explicit freshness request is a hard constraint. Saved
            # defaults stay recall-friendly and let the agent demote unknowns.
            unknown_freshness_excluded += 1
            continue
        survivors.append(row)

    unique: dict[tuple[str, tuple[str, ...]], ApplicationRecord] = {}
    for row in survivors:
        key = _dedupe_work_key(row)
        existing = unique.get(key)
        if existing is None:
            unique[key] = row
            continue
        duplicate_records_excluded += 1
        if _dedupe_work_priority(row) > _dedupe_work_priority(existing):
            unique[key] = row

    matching_count = len(unique)
    review_states = {
        row.id: fit_review_state(row, profile_hash)
        for row in unique.values()
    }
    current_records = [
        row for row in unique.values() if review_states[row.id]["current"]
    ]
    needs_review_records = [
        row for row in unique.values() if not review_states[row.id]["current"]
    ]
    shortlist_args = dict(
        roles=terms,
        skill_terms=skill_terms,
        target_companies=target_companies,
        compensation_floor=requested_floor,
        compensation_currency=effective_currency or None,
    )
    if browse_all:
        rows = _select_work_shortlist(
            list(unique.values()),
            **shortlist_args,
            limit=max(matching_count, 1),
        )
    elif needs_review_records:
        # A static top-50 page permanently stranded row 51 onward once the
        # first page had judgments. Retain a few current rows as global rank
        # anchors and spend the rest of every tool page on the best unseen
        # candidates. Repeated calls therefore resume the sweep.
        anchor_limit = min(len(current_records), min(10, page_size // 5))
        anchors = _select_work_shortlist(
            current_records,
            **shortlist_args,
            limit=max(anchor_limit, 1),
        )[:anchor_limit]
        unseen = _select_work_shortlist(
            needs_review_records,
            **shortlist_args,
            limit=max(page_size - len(anchors), 1),
        )[: page_size - len(anchors)]
        rows = anchors + unseen
    else:
        rows = _select_work_shortlist(
            current_records,
            **shortlist_args,
            limit=page_size,
        )
    results: list[dict[str, Any]] = []
    reviewed_current = 0
    shortlist_needs_review = 0
    for row in rows:
        review = review_states[row.id]
        if review["current"]:
            reviewed_current += 1
        else:
            shortlist_needs_review += 1
        prior = review["fit"]
        # The route only needs ids to reconstruct ORM rows. Avoid building a
        # multi-hundred-row MCP-shaped payload for ordinary board pagination.
        item = {"opportunity_id": row.id} if browse_all else _candidate_payload(row)
        item["assistant_review"] = {
            "state": "current" if review["current"] else "needs_review",
            "reason": review["reason"],
            # Compact anchors only. The explanation already lives on the board;
            # repeating it across 50 tool rows would waste the payload budget.
            "prior_rank": prior.get("rank") if isinstance(prior.get("rank"), int) else None,
            "prior_verdict": prior.get("verdict") if prior.get("verdict") in _FIT_VERDICTS else None,
        }
        results.append(item)
    return {
        "results": results,
        "result_count": len(rows),
        "total_matching": matching_count,
        "reviewed_current_total": len(current_records),
        "needs_review_total": len(needs_review_records),
        "reviewed_current_in_shortlist": reviewed_current,
        "needs_review_in_shortlist": shortlist_needs_review,
        "candidate_queries": terms,
        "filters_applied": {
            "location": effective_location or None,
            "workplace_preference": effective_workplace,
            "compensation_floor": requested_floor,
            "effective_compensation_floor": effective_floor,
            "compensation_currency": effective_currency or None,
            "salary_flex": salary_flex,
            "match_strictness": strictness,
            "exclude_staffing_agencies": exclude_staffing_agencies,
            "posted_within_days": effective_freshness_window,
            "saved_max_days_old": saved_days if use_saved_preferences else None,
            "unknown_freshness_policy": (
                "exclude"
                if posted_within_days is not None
                or filter_settings.get("drop_missing_dates", False)
                else "keep_for_agent_review"
            ),
        },
        "freshness_filter_summary": {
            "known_stale_excluded": stale_excluded,
            "unknown_date_excluded": unknown_freshness_excluded,
            "title_mismatch_excluded": title_mismatch_excluded,
            "level_mismatch_excluded": level_mismatch_excluded,
            "duplicate_records_excluded": duplicate_records_excluded,
        },
        "ranking_owner": "connected_agent",
        "questboard_funded_ai": False,
        "note": (
            "These are source-grounded candidates prioritized by saved-role, "
            "constraint, skill, source, and freshness signals. Retrieval order "
            "is not a resume-fit verdict; judge only rows marked needs_review."
        ),
    }


def search_side_quests(
    db: Session,
    *,
    kinds: list[str] | None = None,
    query: str = "",
    location: str = "",
    near_me_only: bool = False,
    first_quest_ok: bool | None = None,
    page_size: int = 20,
) -> dict[str, Any]:
    known = {kind.id: kind for kind in get_kinds() if kind.id != _WORK_KIND}
    requested = clean_terms(kinds, limit=len(known))
    invalid = sorted({value for value in requested if value not in known})
    if invalid:
        raise ValueError(f"Unknown Side Quest kinds: {', '.join(invalid)}")
    selected = requested or list(known)
    verticals = [
        value
        for kind_id in selected
        for value in vertical_values_for(kind_id)
        if value not in {"career", "work"}
    ]
    if not verticals:
        # Never fall through to get_applications with an empty vertical list:
        # scoped_applications silently defaults to the career scope, which would
        # leak career jobs into the resume-independent Side Quest lane.
        return {
            "results": [],
            "result_count": 0,
            "total_matching": 0,
            "kinds": selected,
            "resume_used": False,
            "questboard_funded_ai": False,
        }
    page_size = max(1, min(int(page_size), _MAX_RESULTS))
    rows, total = application_service.get_applications(
        db,
        search=" ".join(query.split())[:120] or None,
        location=" ".join(location.split())[:120] or None,
        location_strict=bool(location and near_me_only),
        exclude_dead=True,
        upcoming_only=True,
        first_quest_ok=first_quest_ok,
        sort_by="date_found",
        sort_dir="desc",
        page=1,
        page_size=page_size,
        verticals=verticals,
    )
    return {
        "results": [_candidate_payload(row) for row in rows],
        "result_count": len(rows),
        "total_matching": total,
        "kinds": selected,
        "resume_used": False,
        "questboard_funded_ai": False,
    }


def get_opportunity(db: Session, opportunity_id: int) -> dict[str, Any]:
    record = application_service.get_application(db, int(opportunity_id))
    if record is None:
        raise ValueError("Opportunity not found in this local Questboard")
    payload = _candidate_payload(record, detail=True)
    if not payload["description"] and (record.source or "").lower() == "builtin":
        # BuiltIn's search cards omit their body.  Hydrate only a finalist,
        # preserving fast broad discovery while giving the agent requirements.
        from job_finder.tools.scrapers.builtin import fetch_builtin_detail

        detail = fetch_builtin_detail(record.job_url or "")
        description = str(detail.get("description") or "")
        if description:
            payload["description"] = description
            payload["description_excerpt"] = description[:1200]
            payload["detail_resolution"] = "live_source_page"
            payload["content_hash"] = hashlib.sha256(
                f"{payload['content_hash']}\n{description}".encode("utf-8")
            ).hexdigest()
        direct_url = str(detail.get("direct_application_url") or "")
        if direct_url:
            payload["source"]["direct_application_url"] = direct_url
        if detail.get("date_posted"):
            payload["freshness"]["source_posted_at"] = detail["date_posted"]
            payload["freshness"]["source_date_confidence"] = detail[
                "date_confidence"
            ]
    return payload


def set_opportunity_status(
    db: Session, opportunity_id: int, status: str, notes: str = ""
) -> dict[str, Any]:
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"Unsupported status: {status}")
    record = application_service.update_application(
        db,
        int(opportunity_id),
        status=status,
        notes=" ".join(notes.split())[:2000] if notes else None,
    )
    if record is None:
        raise ValueError("Opportunity not found in this local Questboard")
    return {
        "opportunity_id": record.id,
        "status": record.status,
        "notes": record.notes or "",
        "external_action_performed": False,
    }


_FIT_VERDICTS = {"strong", "good", "reach", "skip"}


def _rebalance_current_fit_ranks(
    db: Session,
    *,
    profile_hash: str,
    changed: list[tuple[ApplicationRecord, dict[str, Any]]],
) -> None:
    """Insert changed rows at their requested global positions, then compact.

    Existing current judgments are anchors. A new row assigned rank 2 is
    inserted at position 2 and shifts the old #2 downward; unchanged rows do
    not need another model pass merely to receive their new integer.
    """

    changed_ids = {record.id for record, _ in changed}
    existing: list[tuple[int, ApplicationRecord]] = []
    for record in db.query(ApplicationRecord).filter(
        ApplicationRecord.vertical.in_(("career", "work")),
        ApplicationRecord.agent_fit_json.isnot(None),
        ApplicationRecord.agent_fit_json != "",
    ).all():
        if record.id in changed_ids:
            continue
        state = fit_review_state(record, profile_hash)
        fit = state["fit"]
        if not state["current"] or fit.get("verdict") == "skip":
            continue
        rank = fit.get("rank")
        existing.append((rank if isinstance(rank, int) and rank > 0 else 1_000_000, record))
    sequence = [record for _rank, record in sorted(existing, key=lambda item: (item[0], item[1].id))]

    insertions: list[tuple[int, int, ApplicationRecord]] = []
    for order, (record, item) in enumerate(changed):
        if item["verdict"] == "skip":
            continue
        requested = item.get("rank")
        desired = requested if isinstance(requested, int) and requested > 0 else 1_000_000
        insertions.append((desired, order, record))

    same_position_count: dict[int, int] = {}
    for desired, _order, record in sorted(insertions, key=lambda item: (item[0], item[1])):
        if desired >= 1_000_000:
            position = len(sequence)
        else:
            offset = same_position_count.get(desired, 0)
            position = min(max(desired - 1 + offset, 0), len(sequence))
            same_position_count[desired] = offset + 1
        sequence.insert(position, record)

    for rank, record in enumerate(sequence, 1):
        fit = _parsed_fit(record)
        if fit.get("rank") == rank:
            continue
        fit["rank"] = rank
        record.agent_fit_json = json.dumps(fit)


def set_work_fit(db: Session, rankings: list[dict[str, Any]]) -> dict[str, Any]:
    """Record the connected assistant's own fit verdict for work rows, keyed by
    opportunity_id, so the board and the results panel can show it.

    Current verdicts for unchanged jobs are retained. Each write stamps the
    posting and profile fingerprints, so changed jobs, resumes, or preferences
    become reviewable without throwing away still-valid work. It writes only a
    local annotation and performs no external action.
    """
    if not isinstance(rankings, list) or not rankings:
        raise ValueError("Provide a non-empty list of {opportunity_id, verdict} rankings.")

    cleaned: list[dict[str, Any]] = []
    for item in rankings:
        if not isinstance(item, dict):
            continue
        try:
            oid = int(item.get("opportunity_id"))
        except (TypeError, ValueError):
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in _FIT_VERDICTS:
            raise ValueError(f"verdict must be one of {sorted(_FIT_VERDICTS)}, got {verdict!r}")
        rank_raw = item.get("rank")
        try:
            rank = int(rank_raw) if rank_raw is not None else None
        except (TypeError, ValueError):
            rank = None
        cleaned.append({
            "opportunity_id": oid,
            "rank": rank,
            "verdict": verdict,
            "why": " ".join(str(item.get("why") or "").split())[:600],
            "caveat": " ".join(str(item.get("caveat") or "").split())[:400],
        })

    if not cleaned:
        raise ValueError("No valid rankings: each needs an integer opportunity_id and a verdict.")

    # Resolve targets BEFORE clearing anything: a run that matches no row (stale
    # or hallucinated ids) must not wipe a prior good run's verdicts. Fit only
    # belongs on career/work rows, never on quest rows.
    matched: list[tuple[ApplicationRecord, dict[str, Any]]] = []
    missing: list[int] = []
    for item in cleaned:
        record = application_service.get_application(db, item["opportunity_id"])
        if record is None or (record.vertical or "career") not in ("career", "work"):
            missing.append(item["opportunity_id"])
            continue
        matched.append((record, item))

    if not matched:
        return {
            "run_id": None,
            "applied": 0,
            "missing_opportunity_ids": missing,
            "external_action_performed": False,
        }

    # Batches of one run share its id. Unlike the old latest-run-only model,
    # starting a run does not clear unchanged judgments: the shortlist tells
    # the assistant which rows are stale, and only those rows need model work.
    #
    # Scoring ~50 jobs in a single write took longer than the run's own
    # timeout and the whole run was thrown away: the pull had finished, the
    # shortlist was in hand, and not one verdict reached the board. Writing in
    # batches means a run that dies late keeps what it already decided.
    #
    prior = agent_run_progress.work_fit_run_id()
    run_id = prior or uuid.uuid4().hex[:12]
    stamped_at = _iso(datetime.now(timezone.utc))
    profile_hash = fit_profile_hash(db)

    if not prior:
        agent_run_progress.set_work_fit_run_id(run_id)

    for record, item in matched:
        record.agent_fit_json = json.dumps({
            "rank": item["rank"],
            "verdict": item["verdict"],
            "why": item["why"],
            "caveat": item["caveat"],
            "run_id": run_id,
            "at": stamped_at,
            "content_hash": _content_hash(record),
            "profile_hash": profile_hash,
            "schema_version": 1,
        })
    _rebalance_current_fit_ranks(db, profile_hash=profile_hash, changed=matched)
    applied = len(matched)

    db.commit()
    return {
        "run_id": run_id,
        "applied": applied,
        "missing_opportunity_ids": missing,
        "external_action_performed": False,
    }


def source_status(db: Session, *, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    runs = (
        db.query(ScrapeRunRecord)
        .order_by(ScrapeRunRecord.started_at.desc())
        .limit(500)
        .all()
    )
    latest: dict[str, ScrapeRunRecord] = {}
    for run in runs:
        latest.setdefault(run.source, run)
        if len(latest) >= limit:
            break
    return {
        "sources": [
            {
                "source": run.source,
                "kind": (kind_for_vertical(run.vertical).id if kind_for_vertical(run.vertical) else run.vertical),
                "checked_at": _iso(run.started_at),
                "finish_reason": run.finish_reason,
                "rows_found": run.rows_found,
                "rows_rejected": run.rows_invalid,
            }
            for run in latest.values()
        ],
        "source_count": len(latest),
        "questboard_funded_ai": False,
    }
