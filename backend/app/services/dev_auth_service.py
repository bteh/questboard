"""Local hosted-auth sandbox for multi-user persona testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from fastapi import HTTPException
import jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.application import ApplicationRecord
from app.models.workspace import (
    FileAsset,
    Profile,
    UsageCounter,
    Workspace,
    WorkspacePreferences,
    WorkspaceResume,
    WorkspaceSearchEvent,
    WorkspaceSearchRun,
)
from app.schemas.dev_auth import DevHostedPersonaSummary
from app.schemas.workspace import CompensationPreference, PlaceSelection, WorkspacePreferences as WorkspacePreferencesSchema


def _auth_error(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _not_enabled() -> HTTPException:
    return HTTPException(status_code=404, detail="Dev hosted auth is not enabled")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _workspace_name(full_name: str) -> str:
    return f"{full_name} sandbox"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def user_id_for_email(email: str) -> str:
    normalized = _normalize_email(email)
    safe = "".join(ch if ch.isalnum() else "-" for ch in normalized)
    compact = "-".join(part for part in safe.split("-") if part)
    return f"dev-{compact[:72] or uuid.uuid4().hex}"


def _place(
    label: str,
    *,
    kind: str = "manual",
    city: str = "",
    region: str = "",
    country: str = "",
    country_code: str = "",
) -> dict[str, Any]:
    return {
        "label": label,
        "kind": kind,
        "city": city,
        "region": region,
        "country": country,
        "country_code": country_code,
        "lat": None,
        "lon": None,
        "provider": "dev-sandbox",
        "provider_id": label,
    }


_DEFAULT_PERSONAS: tuple[dict[str, Any], ...] = (
    {
        "id": "maya-chen",
        "email": "maya.chen@launchboard.dev",
        "full_name": "Maya Chen",
        "headline": "Principal product designer moving deeper into AI tools",
        "background": "Eight years across B2B SaaS, design systems, and high-velocity startup product work.",
        "job_search_focus": "Looking for senior design roles shaping AI copilots, workflow automation, and craft-heavy product teams.",
        "current_title": "Principal Product Designer",
        "current_level": "senior",
        "target_roles": ["Principal Product Designer", "Staff Product Designer", "Design Lead"],
        "keywords": ["AI UX", "design systems", "workflow automation", "B2B SaaS"],
        "preferred_places": [
            _place("Remote", kind="manual"),
            _place("San Francisco, CA", kind="city", city="San Francisco", region="California", country="United States", country_code="US"),
        ],
        "workplace_preference": "remote_friendly",
        "compensation": {
            "currency": "USD",
            "pay_period": "annual",
            "current_comp": 235000,
            "min_base": 210000,
            "target_total_comp": 260000,
            "min_acceptable_tc": 220000,
            "include_equity": True,
        },
        "exclude_staffing_agencies": True,
        "resume_filename": "maya-chen-resume.pdf",
        "resume_text": "\n".join([
            "Maya Chen",
            "Principal Product Designer",
            "San Francisco, CA",
            "",
            "Summary",
            "Principal product designer with 8 years building design systems, workflow tools, and AI-assisted experiences.",
            "Led product design for automation products used by 40,000 plus weekly users across enterprise operations teams.",
            "",
            "Experience",
            "Principal Product Designer, Orbital Workflows, 2022 to present",
            "- Owned end-to-end design for AI copilots that reduced manual case work by 31 percent.",
            "- Built a cross-product design system and partnered with engineering on a React component library.",
            "- Ran customer discovery with operations, support, and product leadership to shape roadmap bets.",
            "",
            "Senior Product Designer, Northstar Cloud, 2019 to 2022",
            "- Redesigned onboarding and admin flows, increasing activation by 18 percent.",
            "- Built reusable patterns for analytics dashboards, permissions, and collaboration tools.",
            "",
            "Skills",
            "AI UX, design systems, Figma, product strategy, user research, prototyping, collaboration",
        ]),
    },
    {
        "id": "diego-alvarez",
        "email": "diego.alvarez@launchboard.dev",
        "full_name": "Diego Alvarez",
        "headline": "Staff data engineer targeting AI platform and infrastructure teams",
        "background": "Ten years in data engineering, backend systems, and analytics platforms for growth-stage companies.",
        "job_search_focus": "Wants staff-level platform roles with durable data systems, applied ML infrastructure, and strong compensation.",
        "current_title": "Staff Data Engineer",
        "current_level": "staff",
        "target_roles": ["Staff Data Engineer", "Staff Platform Engineer", "AI Platform Engineer"],
        "keywords": ["data platform", "streaming", "Spark", "Airflow", "LLM infrastructure"],
        "preferred_places": [
            _place("Remote", kind="manual"),
            _place("Seattle, WA", kind="city", city="Seattle", region="Washington", country="United States", country_code="US"),
        ],
        "workplace_preference": "remote_only",
        "compensation": {
            "currency": "USD",
            "pay_period": "annual",
            "current_comp": 285000,
            "min_base": 240000,
            "target_total_comp": 320000,
            "min_acceptable_tc": 250000,
            "include_equity": True,
        },
        "exclude_staffing_agencies": True,
        "resume_filename": "diego-alvarez-resume.pdf",
        "resume_text": "\n".join([
            "Diego Alvarez",
            "Staff Data Engineer",
            "Seattle, WA",
            "",
            "Summary",
            "Staff data engineer with 10 years building analytics foundations, event pipelines, and ML-ready data infrastructure.",
            "",
            "Experience",
            "Staff Data Engineer, Meridian Labs, 2021 to present",
            "- Led migration from batch ETL to streaming data products powering personalization and fraud detection.",
            "- Built a self-service platform for data contracts, quality checks, and orchestration used by 120 engineers.",
            "- Partnered with ML engineering to productionize feature stores and retrieval pipelines for LLM products.",
            "",
            "Senior Data Engineer, Atlas Commerce, 2017 to 2021",
            "- Scaled Airflow and Spark workloads processing 5 billion events per day.",
            "- Reduced warehouse cost 23 percent through data model consolidation and workload tuning.",
            "",
            "Skills",
            "Python, SQL, Spark, Kafka, Airflow, dbt, AWS, Kubernetes, feature stores, ML platforms",
        ]),
    },
    {
        "id": "olivia-thomas",
        "email": "olivia.thomas@launchboard.dev",
        "full_name": "Olivia Thomas",
        "headline": "Nurse practitioner moving from acute care into telehealth",
        "background": "Seven years across family practice, urgent care, and patient education with strong care-coordination experience.",
        "job_search_focus": "Prioritizing telehealth and hybrid care roles with calmer schedules, patient education, and mission-driven teams.",
        "current_title": "Nurse Practitioner",
        "current_level": "senior",
        "target_roles": ["Nurse Practitioner", "Telehealth Clinician", "Clinical Program Manager"],
        "keywords": ["telehealth", "primary care", "patient education", "care coordination"],
        "preferred_places": [
            _place("Remote", kind="manual"),
            _place("Austin, TX", kind="city", city="Austin", region="Texas", country="United States", country_code="US"),
        ],
        "workplace_preference": "remote_friendly",
        "compensation": {
            "currency": "USD",
            "pay_period": "annual",
            "current_comp": 148000,
            "min_base": 135000,
            "target_total_comp": 160000,
            "min_acceptable_tc": 138000,
            "include_equity": False,
        },
        "exclude_staffing_agencies": True,
        "resume_filename": "olivia-thomas-resume.pdf",
        "resume_text": "\n".join([
            "Olivia Thomas, MSN, FNP-C",
            "Nurse Practitioner",
            "Austin, TX",
            "",
            "Summary",
            "Family nurse practitioner with 7 years delivering patient-centered care, chronic disease management, and care coordination.",
            "",
            "Experience",
            "Nurse Practitioner, Cedar Family Health, 2022 to present",
            "- Managed a panel of 1,800 plus patients across preventive, chronic, and urgent care visits.",
            "- Expanded virtual follow-up workflows that improved hypertension visit completion by 22 percent.",
            "- Partnered with behavioral health and pharmacy teams on patient education programs.",
            "",
            "Family Nurse Practitioner, Northlake Urgent Care, 2019 to 2022",
            "- Delivered high-volume acute care and triage while maintaining patient satisfaction above 95 percent.",
            "",
            "Skills",
            "Telehealth, chronic disease management, patient education, care coordination, EMR workflows",
        ]),
    },
    {
        "id": "jordan-lee",
        "email": "jordan.lee@launchboard.dev",
        "full_name": "Jordan Lee",
        "headline": "Customer success leader pivoting toward operations and AI enablement",
        "background": "Six years leading support and customer success programs for SaaS teams, with a strong process and tooling bias.",
        "job_search_focus": "Searching for revenue operations, customer operations, or enablement roles that use automation instead of manual admin.",
        "current_title": "Customer Success Operations Manager",
        "current_level": "mid",
        "target_roles": ["Customer Operations Manager", "Revenue Operations Manager", "Enablement Program Manager"],
        "keywords": ["customer success", "RevOps", "CRM automation", "process improvement"],
        "preferred_places": [
            _place("New York, NY", kind="city", city="New York", region="New York", country="United States", country_code="US"),
        ],
        "workplace_preference": "location_only",
        "compensation": {
            "currency": "USD",
            "pay_period": "annual",
            "current_comp": 132000,
            "min_base": 125000,
            "target_total_comp": 150000,
            "min_acceptable_tc": 128000,
            "include_equity": True,
        },
        "exclude_staffing_agencies": True,
        "resume_filename": "jordan-lee-resume.pdf",
        "resume_text": "\n".join([
            "Jordan Lee",
            "Customer Success Operations Manager",
            "New York, NY",
            "",
            "Summary",
            "Operations-minded customer success leader focused on scalable processes, CRM hygiene, and automation for post-sales teams.",
            "",
            "Experience",
            "Customer Success Operations Manager, CurrentPath, 2023 to present",
            "- Built renewal forecasting and health score workflows that improved expansion coverage by 19 percent.",
            "- Automated account handoff, QBR prep, and escalation routing using Salesforce and internal AI tools.",
            "",
            "Senior Customer Success Manager, Signal Grid, 2020 to 2023",
            "- Managed enterprise renewals and designed playbooks for onboarding, adoption, and risk mitigation.",
            "",
            "Skills",
            "Customer success, revenue operations, Salesforce, Gainsight, process design, automation, enablement",
        ]),
    },
)


@dataclass(frozen=True)
class DevPersona:
    id: str
    email: str
    full_name: str
    headline: str
    background: str
    job_search_focus: str
    current_title: str
    current_level: str
    target_roles: tuple[str, ...]
    keywords: tuple[str, ...]
    preferred_places: tuple[PlaceSelection, ...]
    workplace_preference: str
    compensation: CompensationPreference
    exclude_staffing_agencies: bool
    resume_filename: str
    resume_text: str
    avatar_url: str = ""

    @property
    def workspace_name(self) -> str:
        return _workspace_name(self.full_name)

    @property
    def preferences(self) -> WorkspacePreferencesSchema:
        return WorkspacePreferencesSchema(
            roles=list(self.target_roles),
            keywords=list(self.keywords),
            preferred_places=list(self.preferred_places),
            workplace_preference=self.workplace_preference,
            max_days_old=14,
            current_title=self.current_title,
            current_level=self.current_level,
            compensation=self.compensation,
            exclude_staffing_agencies=self.exclude_staffing_agencies,
        )

    def summary(self) -> DevHostedPersonaSummary:
        return DevHostedPersonaSummary(
            id=self.id,
            email=self.email,
            full_name=self.full_name,
            avatar_url=self.avatar_url,
            headline=self.headline,
            background=self.background,
            job_search_focus=self.job_search_focus,
            current_title=self.current_title,
            current_level=self.current_level,
            target_roles=list(self.target_roles),
            keywords=list(self.keywords),
            preferred_places=[place.label for place in self.preferred_places],
            workplace_preference=self.workplace_preference,
            resume_filename=self.resume_filename,
        )


def ensure_enabled() -> None:
    if not get_settings().dev_hosted_auth_enabled:
        raise _not_enabled()


def _normalize_persona(data: dict[str, Any]) -> DevPersona:
    compensation = CompensationPreference.model_validate(data.get("compensation") or {})
    preferred_places = tuple(
        PlaceSelection.model_validate(item)
        for item in (data.get("preferred_places") or [])
    )
    return DevPersona(
        id=str(data["id"]).strip(),
        email=str(data["email"]).strip(),
        full_name=str(data["full_name"]).strip(),
        headline=str(data.get("headline") or "").strip(),
        background=str(data.get("background") or "").strip(),
        job_search_focus=str(data.get("job_search_focus") or "").strip(),
        current_title=str(data.get("current_title") or "").strip(),
        current_level=str(data.get("current_level") or "mid").strip() or "mid",
        target_roles=tuple(str(item).strip() for item in (data.get("target_roles") or []) if str(item).strip()),
        keywords=tuple(str(item).strip() for item in (data.get("keywords") or []) if str(item).strip()),
        preferred_places=preferred_places,
        workplace_preference=str(data.get("workplace_preference") or "remote_friendly"),
        compensation=compensation,
        exclude_staffing_agencies=bool(data.get("exclude_staffing_agencies", True)),
        resume_filename=str(data.get("resume_filename") or f"{uuid.uuid4().hex}.pdf").strip(),
        resume_text=str(data.get("resume_text") or "").strip(),
        avatar_url=str(data.get("avatar_url") or "").strip(),
    )


def _personas_path() -> str:
    return get_settings().dev_hosted_personas_path.strip()


def _load_personas(personas_path: str) -> tuple[DevPersona, ...]:
    raw_items: list[dict[str, Any]]
    if personas_path:
        payload = json.loads(Path(personas_path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("DEV_HOSTED_PERSONAS_PATH must contain a JSON array")
        raw_items = [item for item in payload if isinstance(item, dict)]
    else:
        raw_items = [dict(item) for item in _DEFAULT_PERSONAS]

    personas: list[DevPersona] = []
    seen: set[str] = set()
    for item in raw_items:
        persona = _normalize_persona(item)
        if not persona.id or persona.id in seen:
            continue
        seen.add(persona.id)
        personas.append(persona)
    return tuple(personas)


def list_personas() -> list[DevHostedPersonaSummary]:
    ensure_enabled()
    return [persona.summary() for persona in _load_personas(_personas_path())]


def get_persona(persona_id: str) -> DevPersona:
    ensure_enabled()
    for persona in _load_personas(_personas_path()):
        if persona.id == persona_id:
            return persona
    raise HTTPException(status_code=404, detail="Persona not found")


def issue_access_token(persona: DevPersona) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = _utcnow() + timedelta(hours=max(settings.dev_hosted_auth_token_ttl_hours, 1))
    token = jwt.encode(
        {
            "sub": persona.id,
            "aud": settings.supabase_jwt_audience or "authenticated",
            "iss": settings.resolved_dev_hosted_auth_issuer,
            "exp": int(expires_at.timestamp()),
            "iat": int(_utcnow().timestamp()),
            "email": persona.email,
            "email_verified": True,
            "app_metadata": {"provider": "dev-sandbox"},
            "user_metadata": {
                "full_name": persona.full_name,
                "avatar_url": persona.avatar_url,
            },
        },
        settings.resolved_dev_hosted_auth_secret,
        algorithm="HS256",
    )
    return token, expires_at


def issue_access_token_for_user(*, user_id: str, email: str, full_name: str, avatar_url: str = "") -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = _utcnow() + timedelta(hours=max(settings.dev_hosted_auth_token_ttl_hours, 1))
    token = jwt.encode(
        {
            "sub": user_id,
            "aud": settings.supabase_jwt_audience or "authenticated",
            "iss": settings.resolved_dev_hosted_auth_issuer,
            "exp": int(expires_at.timestamp()),
            "iat": int(_utcnow().timestamp()),
            "email": _normalize_email(email),
            "email_verified": True,
            "app_metadata": {"provider": "dev-sandbox"},
            "user_metadata": {
                "full_name": full_name.strip(),
                "avatar_url": avatar_url.strip(),
            },
        },
        settings.resolved_dev_hosted_auth_secret,
        algorithm="HS256",
    )
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.resolved_dev_hosted_auth_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience or "authenticated",
            issuer=settings.resolved_dev_hosted_auth_issuer,
            options={"require": ["sub", "exp", "iss"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise _auth_error(f"Invalid access token: {exc}") from exc


def _build_pdf_bytes(text: str) -> bytes:
    lines = [line.strip()[:88] for line in text.splitlines() if line.strip()]
    if not lines:
        lines = ["Launchboard Dev Persona Resume"]
    escaped = [
        line.encode("ascii", "replace").decode("ascii").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines[:36]
    ]
    content_lines = ["BT", "/F1 12 Tf", "72 760 Td"]
    for index, line in enumerate(escaped):
        if index:
            content_lines.append("0 -16 Td")
        content_lines.append(f"({line}) Tj")
    content_lines.append("ET")
    content = "\n".join(content_lines).encode("ascii")

    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n",
        f"4 0 obj<< /Length {len(content)} >>stream\n".encode("ascii") + content + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def _get_resume_record(db: Session, workspace_id: str) -> WorkspaceResume | None:
    return db.query(WorkspaceResume).filter(WorkspaceResume.workspace_id == workspace_id).first()


def _get_preferences_record(db: Session, workspace_id: str) -> WorkspacePreferences | None:
    return db.query(WorkspacePreferences).filter(WorkspacePreferences.workspace_id == workspace_id).first()


def _cleanup_resume_asset(db: Session, record: WorkspaceResume | None) -> None:
    if not record or not record.file_asset_id:
        return
    asset = db.query(FileAsset).filter(FileAsset.id == record.file_asset_id).first()
    if not asset:
        return
    from app.services import file_storage

    local_path = asset.storage_path if asset.storage_provider == "local" else ""
    file_storage.delete_object(
        bucket=asset.bucket,
        storage_path=asset.storage_path,
        local_path=local_path,
    )
    db.delete(asset)


def _seed_resume(db: Session, workspace: Workspace, owner: Profile, persona: DevPersona, *, reset: bool) -> None:
    record = _get_resume_record(db, workspace.id)
    if record and not reset and record.file_asset_id and record.extracted_text:
        return
    if record:
        _cleanup_resume_asset(db, record)
    else:
        record = WorkspaceResume(workspace_id=workspace.id)
        db.add(record)
        db.flush()

    from app.services import file_storage

    stored = file_storage.save_workspace_file(
        workspace.id,
        kind="resume",
        original_filename=persona.resume_filename,
        content=_build_pdf_bytes(persona.resume_text),
        mime_type="application/pdf",
    )
    asset = FileAsset(
        workspace_id=workspace.id,
        owner_user_id=owner.id,
        kind="resume",
        storage_provider=stored.storage_provider,
        bucket=stored.bucket,
        storage_path=stored.storage_path,
        original_filename=persona.resume_filename,
        mime_type=stored.mime_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        metadata_json=json.dumps({
            "dev_persona_id": persona.id,
            "seeded": True,
        }),
    )
    db.add(asset)
    db.flush()

    record.file_asset_id = asset.id
    record.original_filename = persona.resume_filename
    record.stored_filename = Path(persona.resume_filename).name
    record.file_path = stored.local_path
    record.text_path = ""
    record.storage_provider = stored.storage_provider
    record.storage_path = stored.storage_path
    record.file_sha256 = stored.sha256
    record.mime_type = stored.mime_type
    record.file_size = stored.byte_size
    record.parse_status = "parsed"
    record.parse_warning = ""
    record.extracted_text = persona.resume_text
    record.llm_summary = persona.headline


def _reset_workspace_data(db: Session, workspace_id: str) -> None:
    db.query(ApplicationRecord).filter(ApplicationRecord.workspace_id == workspace_id).delete()
    db.query(UsageCounter).filter(UsageCounter.workspace_id == workspace_id).delete()
    db.query(WorkspaceSearchEvent).filter(WorkspaceSearchEvent.workspace_id == workspace_id).delete()
    db.query(WorkspaceSearchRun).filter(WorkspaceSearchRun.workspace_id == workspace_id).delete()


def _prefs_needs_seed(prefs: WorkspacePreferences | None) -> bool:
    if not prefs:
        return True
    try:
        roles = json.loads(prefs.roles_json or "[]")
    except json.JSONDecodeError:
        roles = []
    try:
        keywords = json.loads(prefs.keywords_json or "[]")
    except json.JSONDecodeError:
        keywords = []
    return not roles and not keywords and not (prefs.current_title or "").strip()


def seed_persona_workspace(db: Session, persona: DevPersona, *, reset: bool = False) -> None:
    profile = db.query(Profile).filter(Profile.id == persona.id).first()
    workspace = db.query(Workspace).filter(Workspace.owner_user_id == persona.id).first()
    if not profile or not workspace:
        raise HTTPException(status_code=500, detail="Persona workspace missing")

    workspace.name = persona.workspace_name
    if reset:
        _reset_workspace_data(db, workspace.id)

    prefs = _get_preferences_record(db, workspace.id)
    if reset or _prefs_needs_seed(prefs):
        from app.services import workspace_service

        workspace_service.save_workspace_preferences(db, workspace.id, persona.preferences)
    _seed_resume(db, workspace, profile, persona, reset=reset)
    db.commit()


def _ensure_blank_preferences(db: Session, workspace_id: str) -> None:
    prefs = _get_preferences_record(db, workspace_id)
    if prefs is not None:
        return
    prefs = WorkspacePreferences(
        workspace_id=workspace_id,
        roles_json="[]",
        keywords_json="[]",
        preferred_places_json="[]",
        workplace_preference="remote_friendly",
        max_days_old=14,
        current_title="",
        current_level="mid",
        compensation_currency="USD",
        compensation_period="annual",
        current_comp=None,
        min_base=None,
        target_total_comp=None,
        min_acceptable_tc=None,
        include_equity=True,
        exclude_staffing_agencies=True,
        include_remote=True,
    )
    db.add(prefs)


def _clear_resume(db: Session, workspace_id: str) -> None:
    record = _get_resume_record(db, workspace_id)
    if not record:
        return
    _cleanup_resume_asset(db, record)
    db.delete(record)


def provision_test_account(
    db: Session,
    *,
    email: str,
    full_name: str,
    reset: bool = False,
) -> tuple[str, str, str]:
    normalized_email = _normalize_email(email)
    normalized_name = " ".join(full_name.split()).strip() or normalized_email.split("@")[0] or "Launchboard User"
    user_id = user_id_for_email(normalized_email)

    from app.services import auth_service

    user = auth_service.HostedUser(
        user_id=user_id,
        email=normalized_email,
        full_name=normalized_name,
        avatar_url="",
        auth_provider="dev-sandbox",
        email_verified=True,
        claims={},
    )
    _, workspace, _ = auth_service.ensure_profile_and_workspace(db, user)

    workspace.name = _workspace_name(normalized_name)
    if reset:
        _reset_workspace_data(db, workspace.id)
        _clear_resume(db, workspace.id)
        prefs = _get_preferences_record(db, workspace.id)
        if prefs is not None:
            db.delete(prefs)
    _ensure_blank_preferences(db, workspace.id)
    db.commit()
    return user_id, normalized_email, normalized_name
