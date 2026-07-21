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
from job_finder.tools.scrapers._utils import _strip_html

_WORK_KIND = "work"
_EXCERPT_CHARS = 1200
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
    new_roles = clean_terms(roles, limit=15) if roles is not None else current.roles
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
        "description_excerpt": _clean_excerpt(record.description),
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
    title_conflicts = title_tokens & _OCCUPATION_CONFLICT_TOKENS
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
    age_days = _source_age_days(record.date_posted)
    found = record.date_found or datetime.min
    return (
        age_days is not None,
        -int(age_days) if age_days is not None else float("-inf"),
        is_direct_source(record.source or ""),
        bool(record.description),
        found,
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
    result_limit: int | None = None,
) -> dict[str, Any]:
    # The human browse board asks for the full in-lane set (result_limit); the
    # agent's MCP path leaves it None and stays capped at _MAX_RESULTS.
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
    effective_cap = max(1, min(int(result_limit), 400)) if result_limit else _MAX_RESULTS
    page_size = max(1, min(int(page_size), effective_cap))
    candidate_page_size = min(1000, max(page_size * 10, 200))

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
    rows, _ = application_service.get_applications(
        db,
        title_token_groups=role_groups or None,
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

    stale_excluded = 0
    unknown_freshness_excluded = 0
    title_mismatch_excluded = 0
    duplicate_records_excluded = 0

    # Apply title + freshness BEFORE dedup. Deduping first let a stale-known
    # record win its key and then get freshness-excluded, silently evicting a
    # still-live unknown-date duplicate that shared the key.
    survivors: list[ApplicationRecord] = []
    for row in rows:
        if terms and not _title_is_in_lane(row.job_title, terms):
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

    rows = sorted(
        unique.values(),
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
            "duplicate_records_excluded": duplicate_records_excluded,
        },
        "ranking_owner": "connected_agent",
        "questboard_funded_ai": False,
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


def set_work_fit(db: Session, rankings: list[dict[str, Any]]) -> dict[str, Any]:
    """Record the connected assistant's own fit verdict for work rows, keyed by
    opportunity_id, so the board and the results panel can show it.

    This REPLACES any prior run's verdicts (clears them first), so the board
    only ever reflects the latest run. It writes nothing but a local annotation
    on rows the agent already retrieved; it performs no external action.
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

    run_id = uuid.uuid4().hex[:12]
    stamped_at = _iso(datetime.now(timezone.utc))

    # Clear the previous run's verdicts (career/work only) so the board shows
    # only the latest run, then write this run's.
    db.query(ApplicationRecord).filter(
        ApplicationRecord.vertical.in_(("career", "work")),
        ApplicationRecord.agent_fit_json.isnot(None),
        ApplicationRecord.agent_fit_json != "",
    ).update({ApplicationRecord.agent_fit_json: ""}, synchronize_session=False)

    for record, item in matched:
        record.agent_fit_json = json.dumps({
            "rank": item["rank"],
            "verdict": item["verdict"],
            "why": item["why"],
            "caveat": item["caveat"],
            "run_id": run_id,
            "at": stamped_at,
        })
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
