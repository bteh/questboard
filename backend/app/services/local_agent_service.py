"""Local, model-free tools for Questboard's agent integrations.

The MCP adapter is intentionally thin.  This module owns the useful behavior
so it can be tested without starting an MCP transport and reused by another
local client later.  Nothing here constructs or calls an LLM.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.models.application import ApplicationRecord
from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume
from app.services import application_service, workspace_service
from job_finder.job_trust import is_direct_source
from job_finder.kinds import get_kinds, kind_for_vertical, vertical_values_for
from job_finder.models.database import ScrapeRunRecord

_WORK_KIND = "work"
_MAX_RESULTS = 50
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
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


def resume_for_matching(
    db: Session, workspace_id: str | None = None
) -> dict[str, Any]:
    """Return the local resume only for an explicitly requested agent match."""

    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return {"available": False, "resume_text": "", "reason": "No local profile"}
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
) -> tuple[list[str], str, str, int, float | None]:
    workspace = resolve_local_workspace(db, workspace_id)
    if workspace is None:
        return [], "", "remote_friendly", 14, None
    preferences = workspace_service.get_workspace_preferences(db, workspace.id)
    place = next(
        (
            item.label
            for item in preferences.preferred_places
            if item.label.strip().lower() not in {"remote", "anywhere"}
        ),
        "",
    )
    floor = preferences.compensation.min_base or preferences.compensation.min_acceptable_tc
    role_queries = list(preferences.roles)
    if not role_queries and preferences.current_title:
        role_queries.append(preferences.current_title)
    return (
        role_queries,
        place,
        preferences.workplace_preference,
        preferences.max_days_old,
        floor,
    )


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
            "bucket": record.match_bucket or "unclassified",
            "method": record.rank_source or "unclassified",
            "reasons": _json_list(record.match_reasons_json, limit=3),
            "is_fit_assessment": False,
        },
        "status": record.status or "found",
        "description_excerpt": (record.description or "")[:1200],
    }
    if detail:
        payload.update(
            {
                "description": record.description or "",
                "description_is_untrusted_source_content": True,
                "content_hash": _content_hash(record),
                "requirements_evidence": record.score_evidence,
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
    "mgr": "manager",
    "operations": "ops",
    "stewardship": "steward",
    "sr": "senior",
}
_ROLE_FILLER_TOKENS = frozenset({"a", "an", "and", "of", "the"})


def _role_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+", str(value or "").lower()):
        if raw in _ROLE_FILLER_TOKENS:
            continue
        tokens.add(_ROLE_TOKEN_ALIASES.get(raw, raw))
    return tokens


def _title_matches_queries(title: str | None, queries: list[str]) -> bool:
    """Require a candidate title to contain one configured role family.

    The generic application search also scans descriptions and companies.
    That is useful for free-text browsing but made the profile board admit
    unrelated jobs merely because their description mentioned a target role.
    """

    title_tokens = _role_tokens(title)
    return any(
        bool(query_tokens) and query_tokens.issubset(title_tokens)
        for query_tokens in (_role_tokens(query) for query in queries)
    )


def _source_age_days(value: str | None) -> float | None:
    """Normalize exact and human-readable source dates into an age in days."""

    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return None
    lowered = normalized.lower()
    if re.fullmatch(r"(?:re)?posted\s+today|today", lowered):
        return 0.0
    if re.fullmatch(r"(?:re)?posted\s+yesterday|yesterday", lowered):
        return 1.0

    relative = re.fullmatch(
        r"(?:(?:re)?posted\s+)?(\d+)\s+"
        r"(minute|minutes|hour|hours|day|days)\s+ago",
        lowered,
    )
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        if unit.startswith("minute"):
            return amount / (24 * 60)
        if unit.startswith("hour"):
            return amount / 24
        return float(amount)

    if re.fullmatch(r"\d{10,13}", normalized):
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
    posted_within_days: int | None = None,
    page_size: int = 20,
    use_saved_preferences: bool = True,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    saved_terms, saved_location, saved_workplace, saved_days, saved_floor = (
        _saved_search_defaults(db, workspace_id)
    )
    terms = clean_terms(queries)
    if not terms and use_saved_preferences:
        terms = clean_terms(saved_terms)
    effective_location = " ".join(location.split())[:120] or (
        saved_location if use_saved_preferences else ""
    )
    effective_workplace = (
        saved_workplace if workplace_preference == "saved" else workplace_preference
    )
    if effective_workplace not in {"remote_friendly", "remote_only", "location_only"}:
        raise ValueError("workplace_preference must be saved, remote_friendly, remote_only, or location_only")
    effective_floor = compensation_floor
    if effective_floor is None and use_saved_preferences:
        effective_floor = saved_floor
    if posted_within_days is not None:
        posted_within_days = max(1, min(int(posted_within_days), 365))
    effective_freshness_window = posted_within_days
    if effective_freshness_window is None and use_saved_preferences:
        effective_freshness_window = max(1, min(int(saved_days), 365))
    page_size = max(1, min(int(page_size), _MAX_RESULTS))
    candidate_page_size = min(100, max(page_size * 4, page_size))

    # One blank query means "show the board".  Multiple role families are
    # searched independently and merged, avoiding an accidental AND query.
    search_terms: list[str | None] = terms or [None]
    merged: dict[int, ApplicationRecord] = {}
    for term in search_terms:
        rows, _ = application_service.get_applications(
            db,
            search=term,
            is_remote=True if effective_workplace == "remote_only" else None,
            location=effective_location or None,
            location_strict=bool(
                effective_location and effective_workplace == "location_only"
            ),
            salary_min=effective_floor,
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
        for row in rows:
            merged[row.id] = row

    stale_excluded = 0
    unknown_freshness_excluded = 0
    title_mismatch_excluded = 0
    filtered: list[ApplicationRecord] = []
    for row in merged.values():
        if terms and not _title_matches_queries(row.job_title, terms):
            title_mismatch_excluded += 1
            continue
        age_days = _source_age_days(row.date_posted)
        if effective_freshness_window is not None and age_days is not None:
            if age_days > effective_freshness_window:
                stale_excluded += 1
                continue
        elif posted_within_days is not None:
            # An explicit freshness request is a hard constraint. Saved
            # defaults stay recall-friendly and let the agent demote unknowns.
            unknown_freshness_excluded += 1
            continue
        filtered.append(row)

    rows = sorted(
        filtered,
        key=lambda item: item.date_found or datetime.min,
        reverse=True,
    )[:page_size]
    return {
        "results": [_candidate_payload(row) for row in rows],
        "result_count": len(rows),
        "candidate_queries": terms,
        "filters_applied": {
            "location": effective_location or None,
            "workplace_preference": effective_workplace,
            "compensation_floor": effective_floor,
            "posted_within_days": effective_freshness_window,
            "saved_max_days_old": saved_days if use_saved_preferences else None,
            "unknown_freshness_policy": (
                "exclude" if posted_within_days is not None else "keep_for_agent_review"
            ),
        },
        "freshness_filter_summary": {
            "known_stale_excluded": stale_excluded,
            "unknown_date_excluded": unknown_freshness_excluded,
            "title_mismatch_excluded": title_mismatch_excluded,
        },
        "ranking_owner": "connected_agent",
        "server_funded_ai": False,
        "note": (
            "These are source-grounded candidates in newest-first order. "
            "Retrieval signals are not a resume-fit verdict."
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
        "server_funded_ai": False,
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
        "server_funded_ai": False,
    }
