"""Hosted anonymous workspace lifecycle and onboarding helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.workspace import (
    FileAsset,
    Profile,
    UsageCounter,
    WorkerHeartbeat,
    WorkspaceMembership,
    Workspace,
    WorkspaceSearchEvent,
    WorkspacePreferences,
    WorkspaceResume,
    WorkspaceSearchRun,
    WorkspaceSession,
)
from app.schemas.workspace import (
    CompanyTarget,
    CompensationPreference,
    HostedBootstrapResponse,
    HostedFeatureFlags,
    HostedUserProfile,
    HostedWorkspaceSummary,
    OnboardingState,
    PlaceSelection,
    SearchSnapshot,
    WorkspacePreferences as WorkspacePreferencesSchema,
    WorkspaceResumeStatus,
    WorkspaceResumeUploadResponse,
    WorkspaceSessionResponse,
)
from app.services.workspace_naming import allocate_workspace_slug

logger = logging.getLogger(__name__)

# JobSpy boards enabled by default for hosted/workspace searches.
#
# Disabled boards (per residential-IP testing on 2026-05):
#   - Glassdoor   — returns 400 "location not parsed" when location is Remote
#   - ZipRecruiter — Cloudflare 403 "forbidden aa" on every request
#   - Indeed      — sketchy/low-signal listings in prior testing
#   - Google      — heavy 429 / CAPTCHA wall ("/sorry/index"); JobSpy
#                   retries each query ~30× with backoff, burning minutes
#                   per role × location combo. Catastrophic for end-to-end
#                   search latency.
#
# All JobSpy boards are off by default. Pipeline short-circuits the whole
# JobSpy phase when the list is empty (src/job_finder/pipeline.py
# `skip_jobspy`). Plugin scrapers (Ashby, Greenhouse, Lever, BuiltIn,
# Hacker News, Himalayas, Remotive, RemoteOK, WeWorkRemotely, YC, etc.)
# carry the search load — they're API-based and don't hit CAPTCHAs.
#
# Re-enable any board manually if you have a workaround (residential
# proxy, paid API key, etc.).
#
# Indeed is enabled by default: verified live to return LA-metro local
# listings (El Segundo, Santa Monica, Long Beach, Hawthorne) where the plugin
# scrapers are remote-only. The per-board circuit breaker skips it if it ever
# CAPTCHA-walls, so it can't slow a run down. Glassdoor stays off — it returns
# HTTP 400 "location not parsed" for "City, ST" inputs.
_DEFAULT_JOBSPY_BOARDS: list[str] = ["indeed"]
_LINKEDIN_JOBSPY_BOARD = "linkedin"
_DESKTOP_SESSION_HEADER = "X-Questboard-Session"

_TITLE_KEYWORDS = {
    "engineer", "engineering", "manager", "director", "designer", "analyst",
    "scientist", "developer", "architect", "consultant", "specialist",
    "coordinator", "practitioner", "teacher", "recruiter", "operations",
    "marketing", "product", "success", "revenue", "platform", "nurse",
}
_DATE_TOKENS = {
    "january", "jan", "february", "feb", "march", "mar", "april", "apr",
    "may", "june", "jun", "july", "jul", "august", "aug", "september", "sep",
    "october", "oct", "november", "nov", "december", "dec", "present",
}
# Month tokens that are also ordinary English words. Excluded from the
# last-resort title anchor so prose like "...who may lead marketing teams"
# doesn't read as a date that a job title must precede.
_AMBIGUOUS_MONTH_WORDS = {"may", "march", "mar"}
_RESUME_STOP_TOKENS = {
    "work", "experience", "summary", "skills", "projects", "education",
    "linkedin", "phone", "email", "remote", "hybrid", "onsite", "on-site",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _workspace_ttl() -> timedelta:
    settings = get_settings()
    return timedelta(days=max(settings.workspace_ttl_days, 1))


def _workspace_root(workspace_id: str) -> Path:
    settings = get_settings()
    return Path(settings.resolved_workspace_storage_dir) / workspace_id


def _clean_string_list(values: Any, limit: int = 25) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return cleaned


# ── Watched-companies store ──────────────────────────────────────────────────
# ``target_companies_json`` holds the user's company NAMES (the source of truth
# for which companies to watch). ``target_companies_meta_json`` caches each
# name's resolved ATS board so the pull scrapes it directly — no lossy
# re-discovery — and an exotic Workday / BILL token survives to the scraper.
# The two are kept aligned by case-insensitive name.


def _full_company_entry(data: dict[str, Any], fallback_name: str = "") -> dict[str, Any]:
    return {
        "name": (str(data.get("name") or fallback_name) or "").strip(),
        "slug": str(data.get("slug", "") or ""),
        "ats": str(data.get("ats", "") or ""),
        "job_count": int(data.get("job_count", 0) or 0),
        "careers_url": str(data.get("careers_url", "") or ""),
    }


def _company_is_confirmed(entry: dict[str, Any] | None) -> bool:
    return bool(entry and entry.get("ats") not in ("", "unknown") and entry.get("slug"))


def _load_company_names(record: WorkspacePreferences | None) -> list[str]:
    if not record:
        return []
    try:
        raw = json.loads(record.target_companies_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return _clean_string_list(raw, 60)


def _load_company_meta(record: WorkspacePreferences | None) -> dict[str, dict[str, Any]]:
    """Return the resolved-board cache keyed by lowercased company name."""
    if not record:
        return {}
    try:
        raw = json.loads(getattr(record, "target_companies_meta_json", None) or "[]")
    except (json.JSONDecodeError, TypeError):
        return {}
    meta: dict[str, dict[str, Any]] = {}
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            entry = _full_company_entry(item)
            meta[entry["name"].lower()] = entry
    return meta


def _persist_companies(
    db: Session,
    record: WorkspacePreferences,
    names: list[str],
    meta: dict[str, dict[str, Any]],
) -> None:
    """Write names + meta, pruning meta to the current names and keeping order."""
    cleaned = _clean_string_list(names, 60)
    record.target_companies_json = json.dumps(cleaned)
    record.target_companies_meta_json = json.dumps(
        [
            {**meta[name.lower()], "name": name}
            for name in cleaned
            if name.lower() in meta
        ]
    )
    db.commit()


def _companies_response(record: WorkspacePreferences | None) -> list[dict[str, Any]]:
    """Build the Companies-tab list from the stored names + resolved cache.

    Pure: never touches the network. A name with no confirmed board renders as
    an ``unknown`` row so the UI can ask for the careers link.
    """
    names = _load_company_names(record)
    meta = _load_company_meta(record)
    out: list[dict[str, Any]] = []
    for name in names:
        entry = meta.get(name.lower())
        if _company_is_confirmed(entry):
            out.append(
                {
                    "name": name,
                    "slug": entry["slug"],
                    "ats": entry["ats"],
                    "job_count": entry["job_count"],
                    "careers_url": entry["careers_url"],
                }
            )
        else:
            out.append({"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""})
    return out


def _reconcile_company_meta(record: WorkspacePreferences | None, names: list[str]) -> str:
    """Meta JSON filtered to ``names`` (drops removed companies), order preserved."""
    meta = _load_company_meta(record)
    return json.dumps(
        [{**meta[name.lower()], "name": name} for name in names if name.lower() in meta]
    )


def get_workspace_companies(db: Session, workspace_id: str) -> dict[str, Any]:
    """Companies-tab read: resolve any never-seen names once, then serve cache.

    Names saved before this store existed (or added elsewhere as bare names)
    carry no cached board. They are resolved here exactly once — via the same
    discovery the pull uses — and the result is cached, so the existing list a
    user already had surfaces with its real ATS info and later reads are free.
    """
    record = _get_workspace_preferences_record(db, workspace_id)
    if not record:
        return {"companies": [], "message": ""}
    names = _load_company_names(record)
    meta = _load_company_meta(record)
    unresolved = [name for name in names if name.lower() not in meta]
    if unresolved:
        from app.services import watchlist_service

        for name in unresolved:
            try:
                entry, _message = watchlist_service.resolve_company_entry(name=name)
            except Exception:
                logger.debug("Company resolve failed for %s", name, exc_info=True)
                entry = {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""}
            meta[name.lower()] = {**entry, "name": name}
        _persist_companies(db, record, names, meta)
    return {"companies": _companies_response(record), "message": ""}


def add_workspace_company(
    db: Session,
    workspace_id: str,
    *,
    name: str = "",
    url: str = "",
) -> dict[str, Any]:
    """Add one company to the workspace store the pull reads.

    Runs the shared discover/resolve flow, appends the NAME to
    target_companies_json, and caches the resolved ats/slug so the pull scrapes
    the board directly without re-discovery. A same-named entry is completed in
    place (so a pasted link can finish an unfinished row). Raises
    ``BoardUrlError`` when a pasted URL is unsupported/unconfirmable.
    """
    from app.services import watchlist_service

    record = _get_workspace_preferences_record(db, workspace_id)
    if not record:
        record = WorkspacePreferences(workspace_id=workspace_id)
        db.add(record)
        db.flush()

    entry, message = watchlist_service.resolve_company_entry(name=name, url=url)
    display_name = entry["name"]
    if not display_name:
        raise HTTPException(status_code=400, detail="Company name or careers link is required")

    names = _load_company_names(record)
    meta = _load_company_meta(record)
    key = display_name.lower()
    for index, existing in enumerate(names):
        if existing.lower() == key:
            names[index] = display_name
            break
    else:
        names.append(display_name)
    meta[key] = {**entry, "name": display_name}

    _persist_companies(db, record, names, meta)
    return {"companies": _companies_response(record), "message": message}


def remove_workspace_company(db: Session, workspace_id: str, name: str) -> dict[str, Any]:
    """Remove a company (and its cached board) from the workspace store."""
    record = _get_workspace_preferences_record(db, workspace_id)
    if not record:
        return {"companies": [], "message": ""}
    key = (name or "").strip().lower()
    names = [existing for existing in _load_company_names(record) if existing.lower() != key]
    meta = {k: v for k, v in _load_company_meta(record).items() if k != key}
    _persist_companies(db, record, names, meta)
    return {"companies": _companies_response(record), "message": ""}


def build_workspace_watchlist(preferences: WorkspacePreferencesSchema) -> list[dict[str, Any]]:
    """Watchlist entries for the pull, trusting cached tokens first.

    A company with a confirmed cached board keeps its exact ats/slug (so a
    Workday token or a catalog-unknown token like BILL -> billcom reaches the
    scraper verbatim). Names without a confirmed board fall back to live ATS
    discovery, exactly as before.
    """
    from app.services.watchlist_service import build_watchlist_entries

    names = _clean_string_list(preferences.companies, 60)
    meta = {
        target.name.strip().lower(): target
        for target in (preferences.company_targets or [])
        if target.name.strip()
    }
    entries: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for name in names:
        target = meta.get(name.lower())
        if target and target.ats and target.ats != "unknown" and target.slug:
            entries.append(
                {
                    "name": target.name or name,
                    "ats": target.ats,
                    "slug": target.slug,
                    "job_count": target.job_count,
                    "careers_url": target.careers_url,
                }
            )
        else:
            unresolved.append(name)
    if unresolved:
        entries.extend(build_watchlist_entries(unresolved))
    return entries


def _default_place(label: str) -> dict[str, Any]:
    from job_finder.company_classifier import parse_location

    parsed = parse_location(label)
    match_scope = "city"
    kind = "manual"
    if parsed.get("country") == "non-us" and not parsed.get("city"):
        match_scope = "country"
        kind = "country"
    elif parsed.get("state") and not parsed.get("city"):
        match_scope = "region"
        kind = "region"
    elif parsed.get("country_name") and not parsed.get("city") and not parsed.get("state"):
        match_scope = "country"
        kind = "country"

    return {
        "label": label,
        "kind": kind,
        "match_scope": match_scope,
        "city": parsed.get("city", ""),
        "region": parsed.get("state", ""),
        "country": parsed.get("country_name", ""),
        "country_code": parsed.get("country", ""),
        "lat": None,
        "lon": None,
        "provider": "manual",
        "provider_id": "",
    }


def _normalize_place_item(place: dict[str, Any] | PlaceSelection | str) -> dict[str, Any]:
    if isinstance(place, PlaceSelection):
        raw = place.model_dump()
    elif isinstance(place, dict):
        raw = dict(place)
    elif isinstance(place, str) and place.strip():
        raw = {"label": place.strip()}
    else:
        return _default_place("")

    label = str(raw.get("label", "") or "").strip()
    base = _default_place(label)
    kind = str(raw.get("kind", "") or "").strip()
    if kind and not (kind == "manual" and base["kind"] != "manual"):
        base["kind"] = kind
    if raw.get("match_scope"):
        base["match_scope"] = raw["match_scope"]
    for key in ("city", "region", "country", "country_code", "provider", "provider_id"):
        value = raw.get(key)
        if value not in (None, ""):
            base[key] = value
    for key in ("lat", "lon"):
        if raw.get(key) is not None:
            base[key] = raw[key]
    return base


def _serialize_places(places: list[dict[str, Any]] | list[PlaceSelection] | None) -> str:
    normalized: list[dict[str, Any]] = []
    for place in places or []:
        item = _normalize_place_item(place)
        if item.get("label"):
            normalized.append(item)
    return json.dumps(normalized)


def _normalize_local_workspace_identity(db: Session, workspace: Workspace) -> Workspace:
    name = (workspace.name or "").strip()
    if not name or name == "Workspace":
        workspace.name = "Local workspace"

    slug = (workspace.slug or "").strip()
    if not slug or slug == workspace.id:
        workspace.slug = allocate_workspace_slug(
            db,
            "local workspace",
            exclude_workspace_id=workspace.id,
        )

    return workspace


def _deserialize_places(payload: str | None) -> list[PlaceSelection]:
    if not payload:
        return []
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    places: list[PlaceSelection] = []
    for item in raw:
        if isinstance(item, (dict, str)):
            try:
                places.append(PlaceSelection.model_validate(_normalize_place_item(item)))
            except Exception:
                continue
    return places


def _seed_preferences_from_default() -> WorkspacePreferencesSchema:
    if _desktop_mode_enabled():
        return WorkspacePreferencesSchema(
            roles=[],
            keywords=[],
            companies=[],
            preferred_places=[],
            workplace_preference="remote_friendly",
            # Job posts stay open ~30-60 days; 14 hid still-live older ones.
            max_days_old=45,
            include_linkedin_jobs=False,
            current_title="",
            current_level="mid",
            compensation=CompensationPreference(
                currency="USD",
                pay_period="annual",
                current_comp=None,
                min_base=None,
                target_total_comp=None,
                min_acceptable_tc=None,
                include_equity=True,
            ),
            exclude_staffing_agencies=True,
        )

    from app.dependencies import get_config

    cfg = get_config(None)
    career = cfg.get("career_baseline", {})
    comp = cfg.get("compensation", {})
    search = cfg.get("search_settings", {})
    loc_prefs = cfg.get("location_preferences", {})
    watchlist = cfg.get("watchlist", [])
    preferred_locations = loc_prefs.get("preferred_locations") or cfg.get("locations") or []
    preferred_places = [_default_place(label) for label in _clean_string_list(preferred_locations, 10)]
    job_boards = [str(board).strip().lower() for board in cfg.get("job_boards", []) if str(board).strip()]
    return WorkspacePreferencesSchema(
        roles=_clean_string_list(cfg.get("target_roles"), 15),
        keywords=_clean_string_list(cfg.get("keyword_searches"), 20),
        companies=_clean_string_list(
            [entry.get("name", "") for entry in watchlist if isinstance(entry, dict)],
            60,
        ),
        preferred_places=[PlaceSelection.model_validate(place) for place in preferred_places],
        workplace_preference=loc_prefs.get("workplace_preference", "remote_friendly"),
        max_days_old=int(search.get("max_days_old", 30) or 30),
        include_linkedin_jobs=_LINKEDIN_JOBSPY_BOARD in job_boards,
        current_title=str(career.get("current_title", "") or ""),
        current_level=str(career.get("current_level", "") or ""),
        compensation=CompensationPreference(
            currency=str(comp.get("currency", "USD") or "USD"),
            pay_period=str(comp.get("pay_period", "annual") or "annual"),
            current_comp=career.get("current_tc"),
            min_base=comp.get("min_base"),
            target_total_comp=comp.get("target_total_comp"),
            min_acceptable_tc=career.get("min_acceptable_tc"),
            include_equity=bool(comp.get("include_equity", True)),
        ),
        exclude_staffing_agencies=bool(search.get("exclude_staffing_agencies", True)),
    )


def _prefs_to_schema(prefs: WorkspacePreferences | None) -> WorkspacePreferencesSchema:
    if not prefs:
        return _seed_preferences_from_default()
    try:
        roles = json.loads(prefs.roles_json or "[]")
    except json.JSONDecodeError:
        roles = []
    try:
        keywords = json.loads(prefs.keywords_json or "[]")
    except json.JSONDecodeError:
        keywords = []
    try:
        companies = json.loads(prefs.target_companies_json or "[]")
    except json.JSONDecodeError:
        companies = []
    cleaned_companies = _clean_string_list(companies, 60)
    meta = _load_company_meta(prefs)
    company_targets = [
        CompanyTarget(**meta[name.lower()])
        for name in cleaned_companies
        if name.lower() in meta
    ]
    return WorkspacePreferencesSchema(
        roles=_clean_string_list(roles, 15),
        keywords=_clean_string_list(keywords, 20),
        companies=cleaned_companies,
        company_targets=company_targets,
        preferred_places=_deserialize_places(prefs.preferred_places_json),
        workplace_preference=prefs.workplace_preference or "remote_friendly",
        max_days_old=int(prefs.max_days_old or 30),
        include_linkedin_jobs=bool(getattr(prefs, "include_linkedin_jobs", False)),
        current_title=prefs.current_title or "",
        # Empty current_level disables the level filter. Legacy rows that had
        # a stored value still surface it; new users get "" which is the
        # widest possible default.
        current_level=prefs.current_level or "",
        compensation=CompensationPreference(
            currency=prefs.compensation_currency or "USD",
            pay_period=prefs.compensation_period or "annual",
            current_comp=prefs.current_comp,
            min_base=prefs.min_base,
            target_total_comp=prefs.target_total_comp,
            min_acceptable_tc=prefs.min_acceptable_tc,
            include_equity=bool(prefs.include_equity),
        ),
        exclude_staffing_agencies=bool(prefs.exclude_staffing_agencies),
        match_strictness=_clean_strictness(getattr(prefs, "match_strictness", None)),
    )


_VALID_STRICTNESS = {"loose", "balanced", "strict"}


def _clean_strictness(value: str | None) -> str:
    """Normalize stored strictness; fall back to 'balanced' for empty/legacy rows.

    Balanced is the default because it sits between 'loose' (high recall, low
    precision — surfaces too many off-target roles) and 'strict' (high
    precision, low recall — easy to miss legit matches with title variation).
    Empty values from old workspace rows that predate this column also map
    here so users don't get an unexpectedly wide net.
    """
    if not value:
        return "balanced"
    candidate = str(value).strip().lower()
    return candidate if candidate in _VALID_STRICTNESS else "balanced"


def _resume_to_schema(resume: WorkspaceResume | None) -> WorkspaceResumeStatus:
    if not resume:
        return WorkspaceResumeStatus()
    parse_status = resume.parse_status or "missing"
    if parse_status not in {"missing", "parsed", "warning", "error"}:
        parse_status = "error"
    return WorkspaceResumeStatus(
        exists=bool(resume.file_path or resume.storage_path or resume.file_asset_id),
        filename=resume.original_filename or "",
        file_size=int(resume.file_size or 0),
        parse_status=parse_status,
        parse_warning=resume.parse_warning or "",
    )


@dataclass
class WorkspaceContext:
    workspace: Workspace
    session: WorkspaceSession | None = None
    profile: Profile | None = None
    membership: WorkspaceMembership | None = None
    auth_subject: str | None = None


def _authenticate_hosted_user(db: Session, request: Request) -> WorkspaceContext:
    from app.services import auth_service

    user = auth_service.authenticate_request(request.headers.get("Authorization"))
    profile, workspace, membership = auth_service.ensure_profile_and_workspace(db, user)
    now = _utcnow()
    profile.last_seen_at = now
    workspace.last_active_at = now
    db.commit()
    return WorkspaceContext(
        workspace=workspace,
        profile=profile,
        membership=membership,
        auth_subject=user.user_id,
    )


def get_hosted_bootstrap(db: Session, request: Request) -> HostedBootstrapResponse:
    context = _authenticate_hosted_user(db, request)
    settings = get_settings()
    return HostedBootstrapResponse(
        hosted_mode=True,
        auth_required=True,
        csrf_required=False,
        llm_optional=True,
        user=HostedUserProfile(
            id=context.profile.id,
            email=context.profile.email,
            full_name=context.profile.full_name,
            avatar_url=context.profile.avatar_url or "",
            auth_provider=context.profile.auth_provider or "supabase",
            email_verified=bool(context.profile.email_verified),
        ),
        workspace=HostedWorkspaceSummary(
            id=context.workspace.id,
            name=context.workspace.name or "Workspace",
            slug=context.workspace.slug or "",
            role=context.membership.role if context.membership else "owner",
            plan=context.workspace.plan or context.profile.plan or "free",
            subscription_status=(
                context.workspace.subscription_status
                or context.profile.subscription_status
                or "inactive"
            ),
        ),
        features=HostedFeatureFlags(
            platform_managed_ai=bool(settings.hosted_platform_managed_ai),
            runtime_llm_configurable=bool(settings.allow_workspace_llm_config),
            billing_enabled=False,
        ),
    )


def cleanup_expired_workspaces(db: Session) -> int:
    from app.models.application import ApplicationRecord

    now = _utcnow()
    expired = db.query(Workspace).filter(Workspace.expires_at < now).all()
    removed = 0
    for workspace in expired:
        db.query(ApplicationRecord).filter(ApplicationRecord.workspace_id == workspace.id).delete()
        db.query(FileAsset).filter(FileAsset.workspace_id == workspace.id).delete()
        db.query(UsageCounter).filter(UsageCounter.workspace_id == workspace.id).delete()
        db.query(WorkspaceMembership).filter(WorkspaceMembership.workspace_id == workspace.id).delete()
        db.query(WorkspaceSession).filter(WorkspaceSession.workspace_id == workspace.id).delete()
        db.query(WorkspaceResume).filter(WorkspaceResume.workspace_id == workspace.id).delete()
        db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace.id).delete()
        db.query(WorkspaceSearchEvent).filter(WorkspaceSearchEvent.workspace_id == workspace.id).delete()
        db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.workspace_id == workspace.id).delete()
        root = _workspace_root(workspace.id)
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        db.delete(workspace)
        removed += 1
    if removed:
        db.commit()
    return removed


def _set_workspace_cookies(response: Response, session_token: str, csrf_token: str, expires_at: datetime) -> None:
    settings = get_settings()
    max_age = int((expires_at - _utcnow()).total_seconds())
    secure = bool(settings.session_secure_cookies)
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _desktop_mode_enabled() -> bool:
    return os.environ.get("QUESTBOARD_DESKTOP_MODE", "").strip().lower() == "true"


def _session_token_from_request(request: Request) -> str | None:
    if _desktop_mode_enabled():
        header_token = (request.headers.get(_DESKTOP_SESSION_HEADER, "") or "").strip()
        if header_token:
            return header_token
    return request.cookies.get(get_settings().session_cookie_name)


def _session_from_cookie(db: Session, session_token: str | None) -> WorkspaceContext | None:
    if not session_token:
        return None
    now = _utcnow()
    token_hash = _hash_token(session_token)
    session = (
        db.query(WorkspaceSession)
        .filter(
            WorkspaceSession.session_token_hash == token_hash,
            WorkspaceSession.revoked == False,  # noqa: E712
            WorkspaceSession.expires_at >= now,
        )
        .first()
    )
    if not session:
        return None
    workspace = db.query(Workspace).filter(Workspace.id == session.workspace_id).first()
    workspace_expires_at = _coerce_utc(workspace.expires_at if workspace else None)
    if not workspace or not workspace_expires_at or workspace_expires_at < now:
        return None
    return WorkspaceContext(workspace=workspace, session=session)


def bootstrap_workspace_session(db: Session, request: Request, response: Response) -> WorkspaceSessionResponse:
    cleanup_expired_workspaces(db)

    settings = get_settings()
    request_session_token = _session_token_from_request(request)
    current = _session_from_cookie(db, request_session_token)
    now = _utcnow()
    expires_at = now + _workspace_ttl()
    csrf_token = secrets.token_urlsafe(24)
    desktop_mode = _desktop_mode_enabled()

    if current:
        _normalize_local_workspace_identity(db, current.workspace)
        current.workspace.last_active_at = now
        current.workspace.expires_at = expires_at
        current.session.last_seen_at = now
        current.session.expires_at = expires_at
        current.session.csrf_token_hash = _hash_token(csrf_token)
        db.commit()
        session_token = request_session_token or request.cookies.get(settings.session_cookie_name, "")
        _set_workspace_cookies(response, session_token, csrf_token, expires_at)
        return WorkspaceSessionResponse(
            workspace_id=current.workspace.id,
            expires_at=expires_at,
            hosted_mode=settings.hosted_mode,
            session_token=session_token if desktop_mode else None,
            csrf_token=csrf_token if desktop_mode else None,
        )

    workspace_id = uuid.uuid4().hex
    session_token = secrets.token_urlsafe(32)
    workspace = Workspace(
        id=workspace_id,
        name="Local workspace",
        slug=allocate_workspace_slug(db, "local workspace"),
        mode="anonymous",
        created_at=now,
        updated_at=now,
        last_active_at=now,
        expires_at=expires_at,
    )
    db.add(workspace)
    db.flush()

    session = WorkspaceSession(
        id=uuid.uuid4().hex,
        workspace_id=workspace_id,
        session_token_hash=_hash_token(session_token),
        csrf_token_hash=_hash_token(csrf_token),
        user_agent=(request.headers.get("user-agent") or "")[:500],
        ip_address=((request.client.host if request.client else "") or "")[:128],
        created_at=now,
        updated_at=now,
        last_seen_at=now,
        expires_at=expires_at,
    )
    db.add(session)

    seeded = _seed_preferences_from_default()
    db.add(
        WorkspacePreferences(
            workspace_id=workspace_id,
            roles_json=json.dumps(seeded.roles),
            keywords_json=json.dumps(seeded.keywords),
            preferred_places_json=_serialize_places(seeded.preferred_places),
            workplace_preference=seeded.workplace_preference,
            max_days_old=seeded.max_days_old,
            include_linkedin_jobs=seeded.include_linkedin_jobs,
            current_title=seeded.current_title,
            current_level=seeded.current_level,
            current_comp=seeded.compensation.current_comp,
            compensation_currency=seeded.compensation.currency,
            compensation_period=seeded.compensation.pay_period,
            min_base=seeded.compensation.min_base,
            target_total_comp=seeded.compensation.target_total_comp,
            min_acceptable_tc=seeded.compensation.min_acceptable_tc,
            include_equity=seeded.compensation.include_equity,
            exclude_staffing_agencies=seeded.exclude_staffing_agencies,
            include_remote=seeded.workplace_preference != "location_only",
        )
    )
    db.commit()

    _set_workspace_cookies(response, session_token, csrf_token, expires_at)
    return WorkspaceSessionResponse(
        workspace_id=workspace_id,
        expires_at=expires_at,
        hosted_mode=settings.hosted_mode,
        session_token=session_token if desktop_mode else None,
        csrf_token=csrf_token if desktop_mode else None,
    )


def require_workspace_context(db: Session, request: Request, *, validate_csrf: bool = False) -> WorkspaceContext:
    settings = get_settings()
    if settings.hosted_mode:
        return _authenticate_hosted_user(db, request)
    session_token = _session_token_from_request(request)
    context = _session_from_cookie(db, session_token)
    if not context:
        raise HTTPException(status_code=401, detail="Session missing or expired")

    if validate_csrf:
        header_token = request.headers.get("X-CSRF-Token", "")
        if _desktop_mode_enabled() and session_token:
            if not header_token or _hash_token(header_token) != context.session.csrf_token_hash:
                raise HTTPException(status_code=403, detail="Invalid CSRF token")
        else:
            cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
            if not cookie_token or not header_token or cookie_token != header_token:
                raise HTTPException(status_code=403, detail="Invalid CSRF token")
            if _hash_token(cookie_token) != context.session.csrf_token_hash:
                raise HTTPException(status_code=403, detail="Invalid CSRF token")

    now = _utcnow()
    expires_at = now + _workspace_ttl()
    context.workspace.last_active_at = now
    context.workspace.expires_at = expires_at
    context.session.last_seen_at = now
    context.session.expires_at = expires_at
    db.commit()
    return context


def get_workspace_context_optional(db: Session, request: Request) -> WorkspaceContext | None:
    settings = get_settings()
    if settings.hosted_mode:
        return _authenticate_hosted_user(db, request)
    context = _session_from_cookie(db, _session_token_from_request(request))
    if not context:
        return None
    now = _utcnow()
    expires_at = now + _workspace_ttl()
    context.workspace.last_active_at = now
    context.workspace.expires_at = expires_at
    context.session.last_seen_at = now
    context.session.expires_at = expires_at
    db.commit()
    return context


def get_workspace_preferences(db: Session, workspace_id: str) -> WorkspacePreferencesSchema:
    prefs = db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace_id).first()
    return _prefs_to_schema(prefs)


def _get_workspace_preferences_record(db: Session, workspace_id: str) -> WorkspacePreferences | None:
    return db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace_id).first()


def save_workspace_preferences(
    db: Session,
    workspace_id: str,
    preferences: WorkspacePreferencesSchema,
    *,
    commit: bool = True,
) -> WorkspacePreferencesSchema:
    """Persist preferences, optionally joining a caller-owned transaction."""
    record = db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace_id).first()
    if not record:
        record = WorkspacePreferences(workspace_id=workspace_id)
        db.add(record)

    record.roles_json = json.dumps(_clean_string_list(preferences.roles, 15))
    record.keywords_json = json.dumps(_clean_string_list(preferences.keywords, 20))
    cleaned_companies = _clean_string_list(preferences.companies, 60)
    # The resolved-board cache is owned by the Companies endpoints, not this
    # general save. Reconcile it against the incoming names (drop removed
    # companies, keep the rest) rather than trusting preferences.company_targets,
    # so a search-prefs POST that omits the cache can never wipe a token.
    record.target_companies_meta_json = _reconcile_company_meta(record, cleaned_companies)
    record.target_companies_json = json.dumps(cleaned_companies)
    record.preferred_places_json = _serialize_places(preferences.preferred_places)
    record.workplace_preference = preferences.workplace_preference
    record.max_days_old = preferences.max_days_old
    record.include_linkedin_jobs = bool(preferences.include_linkedin_jobs)
    record.current_title = preferences.current_title.strip()
    # Empty string is now a valid value — it disables the level filter and
    # is the new default for users who haven't set a current level.
    record.current_level = preferences.current_level.strip()
    record.current_comp = preferences.compensation.current_comp
    record.compensation_currency = preferences.compensation.currency.upper() or "USD"
    record.compensation_period = preferences.compensation.pay_period
    record.min_base = preferences.compensation.min_base
    record.target_total_comp = preferences.compensation.target_total_comp
    record.min_acceptable_tc = preferences.compensation.min_acceptable_tc
    record.include_equity = bool(preferences.compensation.include_equity)
    record.exclude_staffing_agencies = bool(preferences.exclude_staffing_agencies)
    record.include_remote = preferences.workplace_preference != "location_only"
    record.match_strictness = _clean_strictness(preferences.match_strictness)
    if commit:
        db.commit()
    return _prefs_to_schema(record)


def get_workspace_llm(
    db: Session,
    workspace_id: str,
    *,
    fallback_to_global: bool = True,
):
    settings = get_settings()
    if settings.hosted_mode and settings.hosted_platform_managed_ai and not settings.allow_workspace_llm_config:
        fallback_to_global = True
        has_workspace_config = False
    else:
        if _desktop_mode_enabled():
            # The desktop app should behave like a clean end-user workspace
            # instead of silently inheriting developer shell/.env AI settings.
            fallback_to_global = False
        if settings.dev_hosted_auth_enabled and settings.allow_workspace_llm_config:
            # The local hosted sandbox should behave like a real user workspace,
            # not silently inherit the developer's machine-wide .env model.
            fallback_to_global = False
        record = _get_workspace_preferences_record(db, workspace_id)
        has_workspace_config = bool(
            record and (record.llm_provider or record.llm_base_url or record.llm_model)
        )
    if has_workspace_config:
        from job_finder.llm_client import LLMClient

        from job_finder.secrets import decrypt_value

        return LLMClient(
            provider=record.llm_provider or None,
            base_url=record.llm_base_url or None,
            api_key=decrypt_value(record.llm_api_key) or None,
            model=record.llm_model or None,
        )
    if fallback_to_global:
        from app.dependencies import get_llm

        llm = get_llm()
        if llm.is_configured:
            return llm
    return None


def get_workspace_llm_status(db: Session, workspace_id: str) -> dict[str, Any]:
    llm = get_workspace_llm(db, workspace_id, fallback_to_global=True)
    settings = get_settings()
    configured = bool(llm and llm.is_configured)
    available = False
    if configured:
        try:
            available = llm.is_available()
        except Exception:
            available = False
    info = llm.get_provider_info() if llm else {}
    return {
        "configured": configured,
        "available": available,
        "provider": info.get("provider", "") if configured else "",
        "model": info.get("model", "") if configured else "",
        "label": info.get("label", "") if configured else "",
        "runtime_configurable": bool(settings.allow_workspace_llm_config),
    }


def save_workspace_llm_config(
    db: Session,
    workspace_id: str,
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.hosted_mode and not settings.allow_workspace_llm_config:
        raise HTTPException(status_code=403, detail="Hosted AI is platform-managed")
    if settings.hosted_mode and settings.allow_workspace_llm_config and not os.getenv("QUESTBOARD_SECRET"):
        raise HTTPException(
            status_code=503,
            detail="Hosted BYO AI requires QUESTBOARD_SECRET so workspace keys can be stored safely.",
        )
    record = _get_workspace_preferences_record(db, workspace_id)
    if not record:
        seeded = _seed_preferences_from_default()
        record = WorkspacePreferences(
            workspace_id=workspace_id,
            roles_json=json.dumps(seeded.roles),
            keywords_json=json.dumps(seeded.keywords),
            preferred_places_json=_serialize_places(seeded.preferred_places),
            workplace_preference=seeded.workplace_preference,
            max_days_old=seeded.max_days_old,
            include_linkedin_jobs=seeded.include_linkedin_jobs,
            current_title=seeded.current_title,
            current_level=seeded.current_level,
            current_comp=seeded.compensation.current_comp,
            compensation_currency=seeded.compensation.currency,
            compensation_period=seeded.compensation.pay_period,
            min_base=seeded.compensation.min_base,
            target_total_comp=seeded.compensation.target_total_comp,
            min_acceptable_tc=seeded.compensation.min_acceptable_tc,
            include_equity=seeded.compensation.include_equity,
            exclude_staffing_agencies=seeded.exclude_staffing_agencies,
            include_remote=seeded.workplace_preference != "location_only",
        )
        db.add(record)

    record.llm_provider = provider.strip()
    record.llm_base_url = base_url.strip()
    from job_finder.secrets import encrypt_value

    record.llm_api_key = encrypt_value(api_key.strip())
    record.llm_model = model.strip()
    db.commit()
    return get_workspace_llm_status(db, workspace_id)


def test_workspace_llm_connection(db: Session, workspace_id: str) -> dict[str, Any]:
    llm = get_workspace_llm(db, workspace_id, fallback_to_global=True)
    if not llm or not llm.is_configured:
        return {
            "success": False,
            "provider": "",
            "model": "",
            "message": "No LLM provider configured",
        }
    info = llm.get_provider_info()
    try:
        available = llm.is_available()
    except Exception as exc:
        import re

        raw = str(exc)
        # Redact any key-like patterns from error messages
        safe = re.sub(r"Bearer\s+\S+", "Bearer ***", raw)
        safe = re.sub(r"\b(sk-|AIza|gsk_|xai-|key-)\S+", "***", safe)
        if llm.api_key and len(llm.api_key) > 4:
            safe = safe.replace(llm.api_key, "***")
        return {
            "success": False,
            "provider": info.get("provider", ""),
            "model": info.get("model", ""),
            "message": f"Connection failed: {safe}",
        }
    return {
        "success": available,
        "provider": info.get("provider", ""),
        "model": info.get("model", ""),
        "message": "Connected successfully" if available else "Failed to reach LLM endpoint",
    }


def get_workspace_resume(db: Session, workspace_id: str) -> WorkspaceResume | None:
    return db.query(WorkspaceResume).filter(WorkspaceResume.workspace_id == workspace_id).first()


def get_file_asset(db: Session, asset_id: int | None) -> FileAsset | None:
    if not asset_id:
        return None
    return db.query(FileAsset).filter(FileAsset.id == asset_id).first()


def get_resume_text(db: Session, workspace_id: str) -> str:
    record = get_workspace_resume(db, workspace_id)
    if not record or not record.extracted_text:
        return ""
    return record.extracted_text


def _cached_resume_analysis(record: WorkspaceResume | None) -> dict[str, Any] | None:
    """Return the canonical analysis only when it matches the current file hash."""
    if not record or not record.llm_summary or not record.file_sha256:
        return None
    try:
        payload = json.loads(record.llm_summary)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("resume_hash") != record.file_sha256:
        return None
    analysis = payload.get("analysis")
    return analysis if isinstance(analysis, dict) else None


def _consume_managed_resume_analysis(db: Session, workspace_id: str) -> bool:
    """Reserve one managed-AI resume analysis inside the monthly hard cap."""
    settings = get_settings()
    if not (settings.hosted_mode and settings.hosted_platform_managed_ai):
        return True
    limit = max(int(settings.hosted_resume_analyses_per_month), 0)
    period_key = _utcnow().strftime("%Y-%m")
    if limit <= 0:
        return False
    values = {
        "workspace_id": workspace_id,
        "metric": "resume_analysis",
        "period_key": period_key,
        "used_count": 1,
        "limit_count": limit,
    }
    dialect = db.get_bind().dialect.name
    if dialect in {"sqlite", "postgresql"}:
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        statement = insert(UsageCounter).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=["workspace_id", "metric", "period_key"],
            set_={
                "used_count": UsageCounter.used_count + 1,
                "limit_count": limit,
                "updated_at": _utcnow(),
            },
            where=UsageCounter.used_count < limit,
        ).returning(UsageCounter.used_count)
        consumed = db.execute(statement).scalar_one_or_none()
        db.commit()
        return consumed is not None

    # Conservative fallback for other SQLAlchemy dialects.
    record = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.workspace_id == workspace_id,
            UsageCounter.metric == "resume_analysis",
            UsageCounter.period_key == period_key,
        )
        .with_for_update()
        .first()
    )
    if record and int(record.used_count or 0) >= limit:
        return False
    if not record:
        record = UsageCounter(**values)
        db.add(record)
    else:
        record.used_count = int(record.used_count or 0) + 1
        record.limit_count = limit
    db.commit()
    return True


def get_or_create_resume_analysis(
    db: Session,
    workspace_id: str,
) -> tuple[dict[str, Any] | None, str, bool]:
    """Read or create the one canonical analysis for the current resume.

    Returns ``(analysis, status, cached)``. Re-reading the same resume is free;
    only a genuinely new analysis consumes the managed monthly allowance.
    """
    record = get_workspace_resume(db, workspace_id)
    cached = _cached_resume_analysis(record)
    if cached is not None:
        return cached, "completed", True
    if not record or not record.extracted_text:
        return None, "failed", False
    llm = get_workspace_llm(db, workspace_id, fallback_to_global=True)
    if not getattr(llm, "is_configured", False):
        return None, "skipped_no_llm", False
    if not _consume_managed_resume_analysis(db, workspace_id):
        return None, "quota_exhausted", False

    from app.services.resume_analyzer import analyze_resume

    analysis = analyze_resume(record.extracted_text, llm)
    if not analysis:
        return None, "analysis_error", False
    record.llm_summary = json.dumps(
        {"resume_hash": record.file_sha256, "analysis": analysis},
        ensure_ascii=False,
    )
    db.commit()
    return analysis, "completed", False


def materialize_workspace_resume_pdf(db: Session, workspace_id: str) -> str:
    record = get_workspace_resume(db, workspace_id)
    if not record:
        return ""
    if record.file_path and Path(record.file_path).exists():
        return record.file_path

    if record.file_asset_id:
        from app.services import file_storage

        asset = get_file_asset(db, record.file_asset_id)
        if asset:
            return file_storage.materialize_object(
                bucket=asset.bucket,
                storage_path=asset.storage_path,
                local_path="",
                suffix=".pdf",
            )

    if record.storage_path:
        from app.services import file_storage

        return file_storage.materialize_object(
            bucket=get_settings().supabase_storage_bucket,
            storage_path=record.storage_path,
            local_path="",
            suffix=".pdf",
        )
    return ""


def _scan_upload(_file_path: Path) -> tuple[bool, str]:
    """Pluggable hook for file scanning. Default is a no-op for dev/self-hosted use."""
    return True, ""


def save_workspace_resume(
    db: Session,
    workspace_id: str,
    original_filename: str,
    content: bytes,
) -> WorkspaceResumeUploadResponse:
    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

    runtime_root = Path(get_settings().data_dir) / "runtime" / "uploads"
    runtime_root.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}.pdf"
    file_path = runtime_root / stored_filename
    file_path.write_bytes(content)

    clean, warning = _scan_upload(file_path)
    if not clean:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=warning or "Upload rejected by scanner")

    from job_finder.tools.resume_parser_tool import parse_resume
    parsed_text = parse_resume(file_path=str(file_path))
    parse_status = "parsed"
    parse_warning = warning
    extracted_text = ""
    if parsed_text.startswith("WARNING:"):
        parse_status = "warning"
        parse_warning = parsed_text
    elif parsed_text.startswith("ERROR"):
        parse_status = "error"
        parse_warning = parsed_text
    else:
        extracted_text = parsed_text

    storage_record = None
    from app.services import file_storage

    uploaded = file_storage.save_workspace_file(
        workspace_id,
        kind="resume",
        original_filename=original_filename,
        content=content,
        mime_type="application/pdf",
    )

    record = db.query(WorkspaceResume).filter(WorkspaceResume.workspace_id == workspace_id).first()
    if not record:
        record = WorkspaceResume(workspace_id=workspace_id)
        db.add(record)

    prior_asset = get_file_asset(db, record.file_asset_id)
    if prior_asset:
        try:
            file_storage.delete_object(
                bucket=prior_asset.bucket,
                storage_path=prior_asset.storage_path,
                local_path="",
            )
        except Exception:
            logger.warning("Failed to delete prior workspace asset %s", prior_asset.id, exc_info=True)
        db.delete(prior_asset)

    owner_user_id = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    storage_record = FileAsset(
        workspace_id=workspace_id,
        owner_user_id=owner_user_id.owner_user_id if owner_user_id else None,
        kind="resume",
        storage_provider=uploaded.storage_provider,
        bucket=uploaded.bucket,
        storage_path=uploaded.storage_path,
        original_filename=Path(original_filename).name,
        mime_type=uploaded.mime_type,
        byte_size=uploaded.byte_size,
        sha256=uploaded.sha256,
        metadata_json=json.dumps({"parse_status": parse_status}),
    )
    db.add(storage_record)
    db.flush()

    record.original_filename = Path(original_filename).name
    record.stored_filename = stored_filename
    record.file_asset_id = storage_record.id
    record.file_path = uploaded.local_path
    record.text_path = ""
    record.storage_provider = uploaded.storage_provider
    record.storage_path = uploaded.storage_path
    record.file_sha256 = uploaded.sha256
    record.mime_type = "application/pdf"
    record.file_size = len(content)
    record.parse_status = parse_status
    record.parse_warning = parse_warning
    record.extracted_text = extracted_text

    analysis: dict[str, Any] | None = None
    # No text read from the file → "failed" (scanned PDFs still surface
    # parse_code="SCANNED_PDF" below via the `scanned` check).
    analysis_status = "failed"
    derived_roles: list[str] = []
    derived_keywords: list[str] = []
    if extracted_text:
        # Flush the new hash/text first so the cache key is the uploaded file.
        # Suggestions are returned for editing and are not preferences until
        # the user explicitly saves the onboarding form.
        db.flush()
        analysis, analysis_status, _cached = get_or_create_resume_analysis(db, workspace_id)
        # No usable AI analysis (the MCP-only case, or an AI error) would leave
        # the board with no target roles. Fall back to the LOCAL, no-AI
        # extractor so Find Work has intent right after upload, without the
        # person typing roles or connecting an assistant. Only fill in when
        # they have not set roles themselves, so a re-upload never clobbers a
        # real choice; a connected assistant can still refine these later.
        if analysis_status != "completed":
            current_prefs = get_workspace_preferences(db, workspace_id)
            if not current_prefs.roles:
                derived_roles, derived_keywords = derive_search_terms_from_resume(
                    db, workspace_id, current_prefs
                )
                if derived_roles or derived_keywords:
                    save_workspace_preferences(
                        db,
                        workspace_id,
                        current_prefs.model_copy(
                            update={
                                "roles": derived_roles or current_prefs.roles,
                                "keywords": derived_keywords or current_prefs.keywords,
                            }
                        ),
                    )

    db.commit()
    try:
        file_path.unlink(missing_ok=True)
    except Exception:
        pass
    scanned = parse_status != "parsed" and "no text was extracted" in parse_warning
    return WorkspaceResumeUploadResponse(
        resume=_resume_to_schema(record),
        analysis=analysis,
        parse_code="SCANNED_PDF" if scanned else None,
        analysis_status=analysis_status,
        derived_roles=derived_roles,
        derived_keywords=derived_keywords,
    )


def get_onboarding_state(db: Session, workspace_id: str) -> OnboardingState:
    prefs = get_workspace_preferences(db, workspace_id)
    resume = _resume_to_schema(get_workspace_resume(db, workspace_id))
    llm = get_workspace_llm(db, workspace_id, fallback_to_global=True)
    has_started_search = (
        db.query(WorkspaceSearchRun.id)
        .filter(WorkspaceSearchRun.workspace_id == workspace_id)
        .first()
        is not None
    )
    llm_available = False
    if llm and llm.is_configured:
        try:
            llm_available = llm.is_available()
        except Exception:
            llm_available = False
    needs_resume = not resume.exists
    ready_to_search = workspace_search_is_runnable(prefs, resume_exists=resume.exists)
    needs_preferences = not ready_to_search
    return OnboardingState(
        workspace_id=workspace_id,
        has_started_search=has_started_search,
        needs_resume=needs_resume,
        needs_preferences=needs_preferences,
        ready_to_search=ready_to_search,
        resume_warning=resume.parse_warning,
        llm_optional=True,
        llm_available=llm_available,
        resume=resume,
        preferences=prefs,
    )


def derive_search_terms_from_resume(
    db: Session,
    workspace_id: str,
    prefs: Any,
) -> tuple[list[str], list[str]]:
    """Derive roles and keywords from a stored resume when the user didn't specify any.

    Returns (roles, keywords). Uses current_title as a fallback role and
    the LLM analysis summary if available, otherwise extracts basic terms
    from the resume text.
    """
    roles: list[str] = []
    keywords: list[str] = []

    def _clean_candidate(value: str) -> str:
        candidate = re.sub(r"\s+", " ", value).strip(" ,-/")
        if candidate.count(",") >= 2:
            candidate = candidate.split(",", 1)[0].strip()
        return candidate[:120]

    def _looks_like_title(value: str) -> bool:
        lowered = value.lower()
        if len(value) < 5 or len(value) > 120:
            return False
        if len(value.split()) < 2:
            return False
        if "@" in value or "http" in lowered:
            return False
        if not any(keyword in lowered for keyword in _TITLE_KEYWORDS):
            return False
        if any(token in lowered for token in ("work experience", "professional summary", "curriculum vitae")):
            return False
        # Reject a bare rank fragment like "Manager ," — a real title carries a
        # domain word too, so let the fragment reconstruction rebuild it.
        words = re.findall(r"[A-Za-z][A-Za-z&/+-]*", value)
        if words and all(word.lower() in _SENIORITY_HEADS for word in words):
            return False
        return True

    _SENIORITY_HEADS = (
        "manager", "director", "lead", "head", "principal", "architect",
        "engineer", "analyst", "scientist", "designer", "developer",
        "specialist", "consultant", "officer", "administrator",
    )

    def _normalize_role(title: str) -> str:
        """Turn "Manager, Data Engineering" into "Data Engineering Manager" and
        trim anything after a divider, so the role reads like a job title.

        Only swap when the comma-tail is a domain (carries a title keyword like
        "engineering"). "Senior Engineer, Google" has an employer after the
        comma, not a domain, so drop the tail and keep the rank rather than
        producing "Google Senior Engineer". (A tail that keeps a trailing
        employer token, e.g. "Data Engineering Google", is a rarer fragmented-
        PDF case we don't try to strip — no reliable company signal without a
        dictionary, and the connected agent or a manual edit corrects it.)"""
        title = re.sub(r"\s+", " ", title).strip(" ,-–—|")
        head, sep, tail = title.partition(",")
        head, tail = head.strip(), tail.strip()
        if sep and tail and head.split() and head.split()[-1].lower() in _SENIORITY_HEADS:
            if any(keyword in tail.lower() for keyword in _TITLE_KEYWORDS):
                tail = re.split(r"\s[-–—|]\s|\s{2,}", tail)[0].strip()
                title = f"{tail} {head}"
            else:
                title = head
        else:
            title = re.split(r"\s[-–—|]\s", title)[0].strip()
        return title[:120]

    def _reconstruct_fragmented_title(compact: list[str]) -> str:
        """Some PDFs break a title across per-token lines ("Manager ," / "Data"
        / "Engineering"). Rejoin the seniority line with the short domain
        fragments that follow it."""
        start = 0
        for idx, line in enumerate(compact):
            if re.sub(r"[^a-z]", "", line.lower()) in (
                "experience", "workexperience", "professionalexperience", "employment", "employmenthistory",
            ):
                start = idx + 1
                break
        for idx in range(start, min(start + 25, len(compact))):
            line = compact[idx]
            if len(line) > 45 or not any(h in line.lower() for h in _SENIORITY_HEADS):
                continue
            parts = [line]
            seen_domain: set[str] = set()
            for nxt in compact[idx + 1 : idx + 7]:
                low = nxt.lower()
                if not nxt or len(nxt) > 45 or nxt in ("-", "–", "—", "•", "·", "|"):
                    break
                first = re.split(r"[\s,]+", low)[0].strip(".,")
                # A year, a month, or a section word ends the title.
                if re.search(r"(19|20)\d{2}|present", low) or first in _DATE_TOKENS:
                    break
                if first in _RESUME_STOP_TOKENS:
                    break
                # A repeated leading word starts the next phrase (the team or
                # department), e.g. "Manager, Data Engineering" then "Data
                # Platform" — stop before the title runs into the department.
                if first in seen_domain:
                    break
                seen_domain.add(first)
                parts.append(nxt)
                if any(divider in nxt for divider in ("-", "–", "—")):
                    break
            candidate = _normalize_role(" ".join(parts))
            if len(candidate.split()) >= 2 and _looks_like_title(candidate):
                return candidate
        return ""

    def _extract_title_from_text(text: str) -> str:
        lines = [
            re.sub(r"\s+", " ", line).strip(" \t•●·|-")
            for line in text.splitlines()
        ]
        compact_lines = [line for line in lines if line]

        for line in compact_lines[:30]:
            if _looks_like_title(line):
                return _clean_candidate(line)

        reconstructed = _reconstruct_fragmented_title(compact_lines)
        if reconstructed:
            return reconstructed

        tokens = re.findall(r"\([A-Za-z][A-Za-z0-9&/().,+-]*|&|[A-Za-z][A-Za-z0-9&/().,+-]*", text)
        search_window = tokens[:180]
        date_idx = next(
            (
                idx
                for idx, token in enumerate(search_window)
                if (
                    token.lower().strip(".,") in _DATE_TOKENS
                    and token.lower().strip(".,") not in _AMBIGUOUS_MONTH_WORDS
                )
                or re.fullmatch(r"(19|20)\d{2}", token)
            ),
            None,
        )
        if date_idx is None:
            return ""

        collected: list[str] = []
        for token in reversed(search_window[max(0, date_idx - 18):date_idx]):
            lowered = token.lower().strip(".,")
            if lowered in _RESUME_STOP_TOKENS:
                if collected:
                    break
                continue
            if token.isdigit():
                if collected:
                    break
                continue
            collected.append(token)
            if len(collected) >= 10:
                break

        # Normalize so an employer that trails a comma ("Manager, Netflix") is
        # dropped here too, not just in the reconstruction path.
        candidate = _normalize_role(_clean_candidate(" ".join(reversed(collected))))
        return candidate if _looks_like_title(candidate) else ""

    # 1) Use roles and keywords already saved in preferences (from prior
    #    resume upload analysis or user edits)
    if prefs.roles:
        roles.extend(prefs.roles)
    if prefs.keywords:
        keywords.extend(prefs.keywords)

    # 2) Use current_title as a fallback role
    if prefs.current_title and prefs.current_title not in roles:
        roles.append(prefs.current_title)

    # 3) Try LLM analysis stored on the resume record — this persists
    #    suggested_target_roles and suggested_keywords from the upload
    #    analysis even if preferences were later cleared
    record = get_workspace_resume(db, workspace_id)
    if record and record.llm_summary:
        try:
            summary = _cached_resume_analysis(record) or json.loads(record.llm_summary)
            industry = summary.get("industry", "")
            if industry and industry != "unknown" and industry not in keywords:
                keywords.append(industry)
            analyzed_title = str(summary.get("current_title") or "").strip()
            if analyzed_title and analyzed_title not in roles:
                roles.append(analyzed_title)
            for role in summary.get("suggested_target_roles", []):
                if role and role not in roles:
                    roles.append(role)
            for kw in summary.get("suggested_keywords", []):
                if kw and kw not in keywords:
                    keywords.append(kw)
        except (json.JSONDecodeError, TypeError):
            pass

    # 4) If still no roles, extract from resume text (basic heuristic)
    if not roles and record and record.extracted_text:
        candidate = _extract_title_from_text(record.extracted_text)
        if candidate:
            roles.append(candidate)

    # 5) If still no keywords, extract technical terms from resume text.
    #    This is the last resort when the LLM never analyzed the resume.
    if not keywords and record and record.extracted_text:
        keywords.extend(_extract_keywords_from_text(record.extracted_text))

    return roles[:15], keywords[:20]


def _extract_keywords_from_text(text: str) -> list[str]:
    """Extract technical keywords from resume text without an LLM.

    Scans for known tools, frameworks, platforms, and domain terms by
    matching multi-word and single-word patterns against a curated set.
    Returns up to 15 keywords ordered by appearance (earlier = more prominent).
    """
    # Collapse whitespace so multi-word terms match even when a PDF split them
    # across lines ("Data\nEngineering" -> "data engineering").
    lowered = re.sub(r"\s+", " ", text).lower()
    found: list[str] = []
    seen: set[str] = set()

    # Multi-word terms first (order matters — check longer patterns before shorter)
    multi_word = [
        "Apache Kafka", "Apache Flink", "Apache Spark", "Apache Iceberg", "Apache Airflow",
        "Google Cloud", "Google BigQuery", "Amazon Web Services", "AWS", "Microsoft Azure",
        "Azure DevOps", "CI/CD", "machine learning", "deep learning", "data engineering",
        "data platform", "data pipeline", "data warehouse", "data lake", "data lakehouse",
        "data governance", "data modeling", "data products",
        "natural language processing", "computer vision", "generative AI", "LLM",
        "React Native", "Ruby on Rails", "Node.js", "Next.js", "Vue.js",
        "Spring Boot", "REST API", "GraphQL", "gRPC", "ETL",
        "Confluent Kafka", "Monte Carlo", "Great Expectations",
    ]
    for term in multi_word:
        if term.lower() in lowered and term.lower() not in seen:
            found.append(term)
            seen.add(term.lower())

    # Single-word technical terms
    single_word = [
        "Python", "Java", "Scala", "Golang", "Rust", "TypeScript", "JavaScript",
        "Kubernetes", "Docker", "Terraform", "Ansible",
        "Snowflake", "Databricks", "Redshift", "BigQuery", "Fivetran", "dbt",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "DynamoDB",
        "Tableau", "Looker", "Power BI", "Superset",
        "Spark", "Hadoop", "Presto", "Trino", "Starburst",
        "TensorFlow", "PyTorch", "Scikit-learn", "Pandas", "NumPy",
        "React", "Angular", "Vue", "Django", "Flask", "FastAPI",
        "Figma", "Sketch", "Photoshop", "InDesign",
        "Salesforce", "HubSpot", "Workday", "SAP", "Oracle",
        "HIPAA", "SOC2", "GDPR", "PCI", "FedRAMP",
        "Agile", "Scrum", "Kanban", "JIRA", "Confluence",
        "n8n", "Cube", "Airbyte", "Dagster", "Prefect", "Meltano",
    ]
    # Use word boundary matching for single words
    for term in single_word:
        if term.lower() in seen:
            continue
        # Check case-insensitive but as a whole word
        if re.search(r'\b' + re.escape(term) + r'\b', text, re.IGNORECASE):
            found.append(term)
            seen.add(term.lower())

    return found[:15]


def place_labels(places: list[PlaceSelection]) -> list[str]:
    return [place.label for place in places if place.label.strip()]


def _meaningful_place_labels(places: list[PlaceSelection]) -> list[str]:
    ignored = {"remote", "anywhere", "united states", "usa", "us"}
    return [
        place.label
        for place in places
        if place.label.strip() and place.label.strip().lower() not in ignored
    ]


def workspace_locations_are_runnable(preferences: WorkspacePreferencesSchema) -> bool:
    """Return True when the current workplace preference has enough location context to search."""
    if preferences.workplace_preference != "location_only":
        return True
    return bool(_meaningful_place_labels(preferences.preferred_places))


def effective_workplace_preference(
    workplace_preference: str,
    places: list[PlaceSelection] | None = None,
) -> str:
    labels = _meaningful_place_labels(list(places or []))
    if workplace_preference == "remote_friendly" and not labels:
        return "remote_only"
    return workplace_preference


def workspace_search_is_runnable(
    preferences: WorkspacePreferencesSchema,
    *,
    resume_exists: bool = False,
) -> bool:
    """Return True when a hosted workspace has enough information to launch a search."""
    has_search_terms = bool(
        preferences.current_title.strip()
        or preferences.roles
        or preferences.keywords
        or resume_exists
    )
    return has_search_terms and workspace_locations_are_runnable(preferences)


def build_search_snapshot(preferences: WorkspacePreferencesSchema) -> SearchSnapshot:
    return SearchSnapshot(
        roles=preferences.roles,
        keywords=preferences.keywords,
        companies=preferences.companies,
        preferred_places=preferences.preferred_places,
        workplace_preference=preferences.workplace_preference,
        max_days_old=preferences.max_days_old,
        include_linkedin_jobs=preferences.include_linkedin_jobs,
        current_title=preferences.current_title,
        current_level=preferences.current_level,
        compensation=preferences.compensation,
        exclude_staffing_agencies=preferences.exclude_staffing_agencies,
        match_strictness=preferences.match_strictness,
    )


def register_search_run(
    db: Session,
    workspace_id: str,
    run_id: str,
    status: str,
    mode: str,
    snapshot: SearchSnapshot,
    started_at: datetime | None,
    request_payload: dict[str, Any] | None = None,
) -> None:
    record = db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.run_id == run_id).first()
    if not record:
        record = WorkspaceSearchRun(
            workspace_id=workspace_id,
            run_id=run_id,
        )
        db.add(record)
    record.status = status
    record.mode = mode
    record.snapshot_json = snapshot.model_dump_json()
    record.request_json = json.dumps(request_payload or {})
    record.available_at = started_at or _utcnow()
    record.completed_at = None
    record.error = ""
    if started_at:
        record.started_at = started_at
    db.commit()


def get_search_run(
    db: Session,
    workspace_id: str,
    run_id: str,
) -> WorkspaceSearchRun | None:
    return (
        db.query(WorkspaceSearchRun)
        .filter(
            WorkspaceSearchRun.workspace_id == workspace_id,
            WorkspaceSearchRun.run_id == run_id,
        )
        .first()
    )


def list_search_runs(
    db: Session,
    workspace_id: str,
    *,
    limit: int = 20,
) -> list[WorkspaceSearchRun]:
    return (
        db.query(WorkspaceSearchRun)
        .filter(WorkspaceSearchRun.workspace_id == workspace_id)
        .order_by(WorkspaceSearchRun.created_at.desc())
        .limit(limit)
        .all()
    )


def append_search_event(
    db: Session,
    workspace_id: str,
    run_id: str,
    event_type: str,
    payload: str,
) -> WorkspaceSearchEvent:
    record = WorkspaceSearchEvent(
        workspace_id=workspace_id,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(record)
    touch_search_run_heartbeat(db, run_id)
    db.commit()
    db.refresh(record)
    return record


def list_search_events(
    db: Session,
    workspace_id: str,
    run_id: str,
    *,
    after_id: int = 0,
    limit: int = 200,
) -> list[WorkspaceSearchEvent]:
    query = (
        db.query(WorkspaceSearchEvent)
        .filter(
            WorkspaceSearchEvent.workspace_id == workspace_id,
            WorkspaceSearchEvent.run_id == run_id,
        )
        .order_by(WorkspaceSearchEvent.id.asc())
    )
    if after_id > 0:
        query = query.filter(WorkspaceSearchEvent.id > after_id)
    return query.limit(limit).all()


def get_progress_messages(
    db: Session,
    workspace_id: str,
    run_id: str,
    *,
    limit: int = 100,
) -> list[str]:
    rows = (
        db.query(WorkspaceSearchEvent)
        .filter(
            WorkspaceSearchEvent.workspace_id == workspace_id,
            WorkspaceSearchEvent.run_id == run_id,
            WorkspaceSearchEvent.event_type == "progress",
        )
        .order_by(WorkspaceSearchEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [row.payload for row in reversed(rows)]


def update_search_run_status(
    db: Session,
    run_id: str,
    *,
    status: str,
    jobs_found: int = 0,
    jobs_scored: int = 0,
    strong_matches: int = 0,
    error: str = "",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> None:
    record = db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.run_id == run_id).first()
    if not record:
        return
    record.status = status
    record.jobs_found = jobs_found
    record.jobs_scored = jobs_scored
    record.strong_matches = strong_matches
    record.error = error
    if started_at:
        record.started_at = started_at
    if completed_at:
        record.completed_at = completed_at
        record.lease_expires_at = None
        record.claimed_by = ""
    db.commit()


def touch_search_run_heartbeat(db: Session, run_id: str, *, worker_id: str = "") -> None:
    record = db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.run_id == run_id).first()
    if not record:
        return
    now = _utcnow()
    record.heartbeat_at = now
    if worker_id:
        record.claimed_by = worker_id
        record.lease_expires_at = now + timedelta(seconds=get_settings().worker_lease_seconds)
    db.flush()


def get_search_request_payload(run: WorkspaceSearchRun) -> dict[str, Any]:
    if not run.request_json:
        return {}
    try:
        payload = json.loads(run.request_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _claim_search_run_record(record: WorkspaceSearchRun, worker_id: str) -> None:
    now = _utcnow()
    record.status = "running"
    record.attempt_count = int(record.attempt_count or 0) + 1
    record.claimed_by = worker_id
    record.claimed_at = now
    record.heartbeat_at = now
    record.lease_expires_at = now + timedelta(seconds=get_settings().worker_lease_seconds)
    if not record.started_at:
        record.started_at = now


def claim_search_run(db: Session, run_id: str, worker_id: str) -> WorkspaceSearchRun | None:
    now = _utcnow()
    record = db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.run_id == run_id).first()
    if not record:
        return None
    available_at = _coerce_utc(record.available_at)
    if available_at and available_at > now:
        return None

    lease_expires_at = _coerce_utc(record.lease_expires_at)
    lease_expired = bool(lease_expires_at and lease_expires_at < now)
    claimable = record.status == "pending" or (
        record.status == "running" and (record.claimed_by == worker_id or lease_expired)
    )
    if not claimable:
        return None

    _claim_search_run_record(record, worker_id)
    db.commit()
    db.refresh(record)
    return record


def claim_next_search_run(db: Session, worker_id: str) -> WorkspaceSearchRun | None:
    now = _utcnow()
    query = (
        db.query(WorkspaceSearchRun)
        .filter(
            (WorkspaceSearchRun.status == "pending")
            | (
                (WorkspaceSearchRun.status == "running")
                & (WorkspaceSearchRun.lease_expires_at.is_not(None))
                & (WorkspaceSearchRun.lease_expires_at < now)
            )
        )
        .filter(WorkspaceSearchRun.available_at <= now)
        .order_by(WorkspaceSearchRun.available_at.asc(), WorkspaceSearchRun.created_at.asc())
    )

    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    if dialect_name == "postgresql":
        query = query.with_for_update(skip_locked=True)

    record = query.first()
    if not record:
        return None

    _claim_search_run_record(record, worker_id)
    db.commit()
    db.refresh(record)
    return record


def release_search_run_for_retry(
    db: Session,
    run_id: str,
    *,
    error: str,
    retry_seconds: int,
) -> None:
    record = db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.run_id == run_id).first()
    if not record:
        return
    record.status = "pending"
    record.error = error
    record.available_at = _utcnow() + timedelta(seconds=retry_seconds)
    record.claimed_by = ""
    record.lease_expires_at = None
    record.heartbeat_at = None
    db.commit()


def increment_usage_counter(
    db: Session,
    workspace_id: str,
    *,
    metric: str,
    amount: int = 1,
    limit_count: int | None = None,
    period_key: str | None = None,
) -> UsageCounter:
    key = period_key or _utcnow().strftime("%Y-%m")
    record = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.workspace_id == workspace_id,
            UsageCounter.metric == metric,
            UsageCounter.period_key == key,
        )
        .first()
    )
    if not record:
        record = UsageCounter(
            workspace_id=workspace_id,
            metric=metric,
            period_key=key,
        )
        db.add(record)
    record.used_count = int(record.used_count or 0) + amount
    if limit_count is not None:
        record.limit_count = limit_count
    db.commit()
    db.refresh(record)
    return record


def update_worker_heartbeat(
    db: Session,
    worker_id: str,
    *,
    worker_type: str = "search",
    status: str = "idle",
    metadata: dict[str, Any] | None = None,
) -> WorkerHeartbeat:
    record = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_id == worker_id).first()
    if not record:
        record = WorkerHeartbeat(worker_id=worker_id)
        db.add(record)
    record.worker_type = worker_type
    record.status = status
    record.last_seen_at = _utcnow()
    record.metadata_json = json.dumps(metadata or {})
    db.commit()
    db.refresh(record)
    return record


def worker_heartbeat_release(record: WorkerHeartbeat) -> str:
    try:
        metadata = json.loads(record.metadata_json or "{}")
    except Exception:
        return ""
    return str(metadata.get("release", "") or "").strip()


def list_recent_worker_heartbeats(
    db: Session,
    *,
    worker_type: str = "search",
    max_age_seconds: int = 180,
    expected_release: str | None = None,
) -> list[WorkerHeartbeat]:
    cutoff = _utcnow() - timedelta(seconds=max_age_seconds)
    records = (
        db.query(WorkerHeartbeat)
        .filter(
            WorkerHeartbeat.worker_type == worker_type,
            WorkerHeartbeat.last_seen_at >= cutoff,
        )
        .order_by(WorkerHeartbeat.last_seen_at.desc())
        .all()
    )
    if not expected_release:
        return records
    return [record for record in records if worker_heartbeat_release(record) == expected_release]


def build_pipeline_config_override(preferences: WorkspacePreferencesSchema, workspace_id: str) -> dict[str, Any]:
    from job_finder.company_classifier import parse_location

    preferred_places = [place.model_dump() for place in preferences.preferred_places]
    labels = place_labels(preferences.preferred_places)
    preferred_states: list[str] = []
    preferred_cities: list[str] = []
    for label in labels:
        parsed = parse_location(label)
        if parsed["state"] and parsed["state"] not in preferred_states:
            preferred_states.append(parsed["state"])
        if parsed["city"] and parsed["city"] not in preferred_cities:
            preferred_cities.append(parsed["city"])
    effective_preference = effective_workplace_preference(
        preferences.workplace_preference,
        preferences.preferred_places,
    )
    include_remote = effective_preference != "location_only"
    remote_only = effective_preference == "remote_only"
    watchlist = build_workspace_watchlist(preferences)
    job_boards = list(_DEFAULT_JOBSPY_BOARDS)
    if preferences.include_linkedin_jobs:
        job_boards.insert(1, _LINKEDIN_JOBSPY_BOARD)

    # Hosted managed-AI reserves the shared platform LLM for the one-shot resume
    # analysis that sets target_roles, so per-job scoring stays keyword-only and
    # concurrent searches can't starve it. Desktop / BYOK users pay for their
    # own AI, so they keep per-job AI scoring.
    settings = get_settings()
    managed_ai = settings.hosted_mode and settings.hosted_platform_managed_ai
    ai_score_jobs = not managed_ai
    ranking_allowlist = {
        value.strip()
        for value in settings.hybrid_ranking_workspace_ids.split(",")
        if value.strip()
    }
    hybrid_ranking_enabled = bool(
        settings.hybrid_ranking_enabled
        and (not ranking_allowlist or workspace_id in ranking_allowlist)
    )

    return {
        "target_roles": preferences.roles,
        "keyword_searches": preferences.keywords,
        "watchlist": watchlist,
        "job_boards": job_boards,
        "locations": labels + (["Remote"] if include_remote and not remote_only else []),
        "location_preferences": {
            "filter_enabled": bool(labels) or remote_only or not include_remote,
            "preferred_locations": labels,
            "preferred_states": preferred_states,
            "preferred_cities": preferred_cities,
            "preferred_places": preferred_places,
            "remote_only": remote_only,
            "include_remote": include_remote,
            "workplace_preference": effective_preference,
        },
        "career_baseline": {
            "current_title": preferences.current_title,
            "current_level": preferences.current_level,
            "current_tc": preferences.compensation.current_comp or 0,
            "min_acceptable_tc": preferences.compensation.min_acceptable_tc,
        },
        "compensation": {
            "currency": preferences.compensation.currency,
            "pay_period": preferences.compensation.pay_period,
            "min_base": preferences.compensation.min_base or 0,
            "target_total_comp": preferences.compensation.target_total_comp or 0,
            "include_equity": preferences.compensation.include_equity,
        },
        "search_settings": {
            "max_days_old": preferences.max_days_old,
            "exclude_staffing_agencies": preferences.exclude_staffing_agencies,
            "ai_score_jobs": ai_score_jobs,
            "ai_expand_roles": not managed_ai,
            "ai_company_discovery": not managed_ai,
            "ai_enhance_jobs": not managed_ai,
            "hybrid_ranking_enabled": hybrid_ranking_enabled,
        },
        "filters": {
            "strictness": preferences.match_strictness,
        },
        "workspace": {
            "workspace_id": workspace_id,
        },
    }
