"""Hosted anonymous workspace lifecycle and onboarding helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
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
    Workspace,
    WorkspacePreferences,
    WorkspaceResume,
    WorkspaceSearchRun,
    WorkspaceSession,
)
from app.schemas.workspace import (
    CompensationPreference,
    OnboardingState,
    PlaceSelection,
    SearchSnapshot,
    WorkspacePreferences as WorkspacePreferencesSchema,
    WorkspaceResumeStatus,
    WorkspaceSessionResponse,
)

logger = logging.getLogger(__name__)


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


def _default_place(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "kind": "manual",
        "city": "",
        "region": "",
        "country": "",
        "country_code": "",
        "lat": None,
        "lon": None,
        "provider": "manual",
        "provider_id": "",
    }


def _serialize_places(places: list[dict[str, Any]] | list[PlaceSelection] | None) -> str:
    normalized: list[dict[str, Any]] = []
    for place in places or []:
        if isinstance(place, PlaceSelection):
            normalized.append(place.model_dump())
        elif isinstance(place, dict) and place.get("label"):
            item = _default_place(str(place["label"]))
            item.update({k: v for k, v in place.items() if k in item})
            normalized.append(item)
        elif isinstance(place, str) and place.strip():
            normalized.append(_default_place(place.strip()))
    return json.dumps(normalized)


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
        if isinstance(item, dict):
            try:
                places.append(PlaceSelection.model_validate(item))
            except Exception:
                continue
    return places


def _seed_preferences_from_default() -> WorkspacePreferencesSchema:
    from app.dependencies import get_config

    cfg = get_config(None)
    career = cfg.get("career_baseline", {})
    comp = cfg.get("compensation", {})
    search = cfg.get("search_settings", {})
    loc_prefs = cfg.get("location_preferences", {})
    preferred_locations = loc_prefs.get("preferred_locations") or cfg.get("locations") or []
    preferred_places = [_default_place(label) for label in _clean_string_list(preferred_locations, 10)]
    return WorkspacePreferencesSchema(
        roles=_clean_string_list(cfg.get("target_roles"), 15),
        keywords=_clean_string_list(cfg.get("keyword_searches"), 20),
        preferred_places=[PlaceSelection.model_validate(place) for place in preferred_places],
        workplace_preference=loc_prefs.get("workplace_preference", "remote_friendly"),
        max_days_old=int(search.get("max_days_old", 14) or 14),
        current_title=str(career.get("current_title", "") or ""),
        current_level=str(career.get("current_level", "mid") or "mid"),
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
    return WorkspacePreferencesSchema(
        roles=_clean_string_list(roles, 15),
        keywords=_clean_string_list(keywords, 20),
        preferred_places=_deserialize_places(prefs.preferred_places_json),
        workplace_preference=prefs.workplace_preference or "remote_friendly",
        max_days_old=int(prefs.max_days_old or 14),
        current_title=prefs.current_title or "",
        current_level=prefs.current_level or "mid",
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
    )


def _resume_to_schema(resume: WorkspaceResume | None) -> WorkspaceResumeStatus:
    if not resume:
        return WorkspaceResumeStatus()
    parse_status = resume.parse_status or "missing"
    if parse_status not in {"missing", "parsed", "warning", "error"}:
        parse_status = "error"
    return WorkspaceResumeStatus(
        exists=bool(resume.file_path),
        filename=resume.original_filename or "",
        file_size=int(resume.file_size or 0),
        parse_status=parse_status,
        parse_warning=resume.parse_warning or "",
    )


@dataclass
class WorkspaceContext:
    workspace: Workspace
    session: WorkspaceSession


def cleanup_expired_workspaces(db: Session) -> int:
    now = _utcnow()
    expired = db.query(Workspace).filter(Workspace.expires_at < now).all()
    removed = 0
    for workspace in expired:
        db.query(WorkspaceSession).filter(WorkspaceSession.workspace_id == workspace.id).delete()
        db.query(WorkspaceResume).filter(WorkspaceResume.workspace_id == workspace.id).delete()
        db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace.id).delete()
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
    current = _session_from_cookie(db, request.cookies.get(settings.session_cookie_name))
    now = _utcnow()
    expires_at = now + _workspace_ttl()
    csrf_token = secrets.token_urlsafe(24)

    if current:
        current.workspace.last_active_at = now
        current.workspace.expires_at = expires_at
        current.session.last_seen_at = now
        current.session.expires_at = expires_at
        current.session.csrf_token_hash = _hash_token(csrf_token)
        db.commit()
        session_token = request.cookies.get(settings.session_cookie_name, "")
        _set_workspace_cookies(response, session_token, csrf_token, expires_at)
        return WorkspaceSessionResponse(
            workspace_id=current.workspace.id,
            expires_at=expires_at,
            hosted_mode=settings.hosted_mode,
        )

    workspace_id = uuid.uuid4().hex
    session_token = secrets.token_urlsafe(32)
    workspace = Workspace(
        id=workspace_id,
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
    )


def require_workspace_context(db: Session, request: Request, *, validate_csrf: bool = False) -> WorkspaceContext:
    settings = get_settings()
    context = _session_from_cookie(db, request.cookies.get(settings.session_cookie_name))
    if not context:
        raise HTTPException(status_code=401, detail="Session missing or expired")

    if validate_csrf:
        cookie_token = request.cookies.get(settings.csrf_cookie_name, "")
        header_token = request.headers.get("X-CSRF-Token", "")
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
    context = _session_from_cookie(db, request.cookies.get(settings.session_cookie_name))
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
) -> WorkspacePreferencesSchema:
    record = db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace_id).first()
    if not record:
        record = WorkspacePreferences(workspace_id=workspace_id)
        db.add(record)

    record.roles_json = json.dumps(_clean_string_list(preferences.roles, 15))
    record.keywords_json = json.dumps(_clean_string_list(preferences.keywords, 20))
    record.preferred_places_json = _serialize_places(preferences.preferred_places)
    record.workplace_preference = preferences.workplace_preference
    record.max_days_old = preferences.max_days_old
    record.current_title = preferences.current_title.strip()
    record.current_level = preferences.current_level.strip() or "mid"
    record.current_comp = preferences.compensation.current_comp
    record.compensation_currency = preferences.compensation.currency.upper() or "USD"
    record.compensation_period = preferences.compensation.pay_period
    record.min_base = preferences.compensation.min_base
    record.target_total_comp = preferences.compensation.target_total_comp
    record.min_acceptable_tc = preferences.compensation.min_acceptable_tc
    record.include_equity = bool(preferences.compensation.include_equity)
    record.exclude_staffing_agencies = bool(preferences.exclude_staffing_agencies)
    record.include_remote = preferences.workplace_preference != "location_only"
    db.commit()
    return _prefs_to_schema(record)


def get_workspace_llm(
    db: Session,
    workspace_id: str,
    *,
    fallback_to_global: bool = True,
):
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
        "runtime_configurable": True,
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
        from job_finder.secrets import decrypt_value as _  # ensure import works
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


def get_resume_text(db: Session, workspace_id: str) -> str:
    record = get_workspace_resume(db, workspace_id)
    if not record or not record.extracted_text:
        return ""
    return record.extracted_text


def _scan_upload(_file_path: Path) -> tuple[bool, str]:
    """Pluggable hook for file scanning. Default is a no-op for dev/self-hosted use."""
    return True, ""


def save_workspace_resume(
    db: Session,
    workspace_id: str,
    original_filename: str,
    content: bytes,
) -> tuple[WorkspaceResumeStatus, dict[str, Any] | None]:
    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

    root = _workspace_root(workspace_id)
    root.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}.pdf"
    file_path = root / stored_filename
    file_path.write_bytes(content)

    clean, warning = _scan_upload(file_path)
    if not clean:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=warning or "Upload rejected by scanner")

    from job_finder.tools.resume_parser_tool import parse_resume
    from app.services.resume_analyzer import analyze_resume

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

    text_path = root / "resume.txt"
    if extracted_text:
        text_path.write_text(extracted_text, encoding="utf-8")
    elif text_path.exists():
        text_path.unlink()

    record = db.query(WorkspaceResume).filter(WorkspaceResume.workspace_id == workspace_id).first()
    if not record:
        record = WorkspaceResume(workspace_id=workspace_id)
        db.add(record)

    record.original_filename = Path(original_filename).name
    record.stored_filename = stored_filename
    record.file_path = str(file_path)
    record.text_path = str(text_path) if extracted_text else ""
    record.mime_type = "application/pdf"
    record.file_size = len(content)
    record.parse_status = parse_status
    record.parse_warning = parse_warning
    record.extracted_text = extracted_text

    analysis: dict[str, Any] | None = None
    if extracted_text:
        llm = get_workspace_llm(db, workspace_id, fallback_to_global=True)
        analysis = analyze_resume(extracted_text, llm)
        if analysis:
            prefs = get_workspace_preferences(db, workspace_id)
            updated = WorkspacePreferencesSchema.model_validate(
                {
                    **prefs.model_dump(),
                    "roles": analysis.get("suggested_target_roles", prefs.roles),
                    "keywords": analysis.get("suggested_keywords", prefs.keywords),
                    "current_title": analysis.get("current_title") or prefs.current_title,
                    "current_level": analysis.get("seniority") or prefs.current_level,
                }
            )
            save_workspace_preferences(db, workspace_id, updated)
            record.llm_summary = json.dumps(
                {
                    "industry": analysis.get("industry", ""),
                    "seniority": analysis.get("seniority", ""),
                    "years_experience": analysis.get("years_experience", 0),
                }
            )

    db.commit()
    return _resume_to_schema(record), analysis


def get_onboarding_state(db: Session, workspace_id: str) -> OnboardingState:
    prefs = get_workspace_preferences(db, workspace_id)
    resume = _resume_to_schema(get_workspace_resume(db, workspace_id))
    llm = get_workspace_llm(db, workspace_id, fallback_to_global=True)
    llm_available = False
    if llm and llm.is_configured:
        try:
            llm_available = llm.is_available()
        except Exception:
            llm_available = False
    meaningful_places = _meaningful_place_labels(prefs.preferred_places)
    needs_resume = not resume.exists
    has_search_terms = bool(prefs.current_title or prefs.roles or prefs.keywords or meaningful_places)
    needs_preferences = not has_search_terms and not resume.exists
    ready_to_search = resume.exists or has_search_terms
    return OnboardingState(
        workspace_id=workspace_id,
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

    # 1) Use current_title from preferences as a role
    if prefs.current_title:
        roles.append(prefs.current_title)

    # 2) Try LLM analysis stored on the resume record
    record = get_workspace_resume(db, workspace_id)
    if record and record.llm_summary:
        try:
            summary = json.loads(record.llm_summary)
            industry = summary.get("industry", "")
            if industry and industry != "unknown":
                keywords.append(industry)
        except (json.JSONDecodeError, TypeError):
            pass

    # 3) If still no roles, extract from resume text (basic heuristic)
    if not roles and record and record.extracted_text:
        text = record.extracted_text
        # Look for common resume patterns: lines that look like job titles
        # (short capitalized lines near the top, after skipping name/contact)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[1:20]:  # skip first line (usually name)
            # Skip contact info, links, and very long lines
            if len(line) > 60 or "@" in line or "http" in line.lower():
                continue
            if any(ch.isdigit() for ch in line[:4]):  # phone, dates
                continue
            # A short capitalized line is likely a title or section header
            words = line.split()
            if 2 <= len(words) <= 6 and words[0][0].isupper():
                roles.append(line)
                break

    return roles[:5], keywords[:10]


def place_labels(places: list[PlaceSelection]) -> list[str]:
    return [place.label for place in places if place.label.strip()]


def _meaningful_place_labels(places: list[PlaceSelection]) -> list[str]:
    ignored = {"remote", "anywhere", "united states", "usa", "us"}
    return [
        place.label
        for place in places
        if place.label.strip() and place.label.strip().lower() not in ignored
    ]


def build_search_snapshot(preferences: WorkspacePreferencesSchema) -> SearchSnapshot:
    return SearchSnapshot(
        roles=preferences.roles,
        keywords=preferences.keywords,
        preferred_places=preferences.preferred_places,
        workplace_preference=preferences.workplace_preference,
        max_days_old=preferences.max_days_old,
        current_title=preferences.current_title,
        current_level=preferences.current_level,
        compensation=preferences.compensation,
        exclude_staffing_agencies=preferences.exclude_staffing_agencies,
    )


def register_search_run(
    db: Session,
    workspace_id: str,
    run_id: str,
    status: str,
    mode: str,
    snapshot: SearchSnapshot,
    started_at: datetime | None,
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
    if started_at:
        record.started_at = started_at
    db.commit()


def update_search_run_status(
    db: Session,
    run_id: str,
    *,
    status: str,
    jobs_found: int = 0,
    jobs_scored: int = 0,
    strong_matches: int = 0,
    error: str = "",
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
    if completed_at:
        record.completed_at = completed_at
    db.commit()


def build_pipeline_config_override(preferences: WorkspacePreferencesSchema, workspace_id: str) -> dict[str, Any]:
    preferred_places = [place.model_dump() for place in preferences.preferred_places]
    labels = place_labels(preferences.preferred_places)
    include_remote = preferences.workplace_preference != "location_only"
    remote_only = preferences.workplace_preference == "remote_only"

    return {
        "target_roles": preferences.roles,
        "keyword_searches": preferences.keywords,
        "locations": labels + (["Remote"] if include_remote and not remote_only else []),
        "location_preferences": {
            "filter_enabled": bool(labels) or remote_only or not include_remote,
            "preferred_locations": labels,
            "preferred_places": preferred_places,
            "remote_only": remote_only,
            "include_remote": include_remote,
            "workplace_preference": preferences.workplace_preference,
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
        },
        "workspace": {
            "workspace_id": workspace_id,
        },
    }
