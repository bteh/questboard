"""SQLite application tracking database using SQLAlchemy."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ApplicationRecord(Base):
    """Tracks every job application through the pipeline."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Job info
    job_title = Column(String(500), nullable=False)
    company = Column(String(300), nullable=False)
    location = Column(String(300), default="")
    job_url = Column(String(2000), nullable=True, unique=True)
    source = Column(String(100), default="")  # LinkedIn, Indeed, etc.
    description = Column(Text, default="")
    is_remote = Column(Boolean, default=False)
    work_type = Column(String(20), default="")  # remote, hybrid, onsite

    # Salary info
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(16), default="")
    salary_period = Column(String(20), default="")
    salary_min_annualized = Column(Float, nullable=True)
    salary_max_annualized = Column(Float, nullable=True)
    estimated_total_comp = Column(String(200), default="")

    # Scoring
    overall_score = Column(Float, nullable=True)
    technical_score = Column(Float, nullable=True)
    leadership_score = Column(Float, nullable=True)
    platform_building_score = Column(Float, nullable=True)
    comp_potential_score = Column(Float, nullable=True)
    company_trajectory_score = Column(Float, nullable=True)
    culture_fit_score = Column(Float, nullable=True)
    career_progression_score = Column(Float, nullable=True)
    recommendation = Column(String(50), default="")  # STRONG_APPLY, APPLY, MAYBE, SKIP
    score_reasoning = Column(Text, default="")
    key_strengths = Column(Text, default="")  # JSON array
    key_gaps = Column(Text, default="")  # JSON array

    # Company intel
    funding_stage = Column(String(100), nullable=True)
    total_funding = Column(String(100), nullable=True)
    employee_count = Column(String(100), nullable=True)
    company_intel_json = Column(Text, default="")  # Full CompanyIntel as JSON
    company_type = Column(String(50), default="Unknown")  # FAANG+, Big Tech, etc.

    # Application materials
    resume_tweaks_json = Column(Text, default="")  # ResumeOptimization as JSON
    cover_letter = Column(Text, default="")
    evaluation_report_json = Column(Text, default="")  # EvaluationReport as JSON — per-JD requirement mapping, archetype, framing, red flags

    # Application method and profile
    application_method = Column(String(100), default="")  # manual, greenhouse, lever
    profile = Column(String(100), default="default")  # which profile found this job
    search_run_id = Column(String(12), nullable=True)  # links to the pipeline run that found this job
    workspace_id = Column(String(64), nullable=True, index=True)

    # Status tracking
    status = Column(String(50), default="found")
    date_found = Column(DateTime, default=_utcnow)
    date_applied = Column(DateTime, nullable=True)
    date_response = Column(DateTime, nullable=True)

    # Notes
    notes = Column(Text, default="")
    contact_name = Column(String(300), default="")
    contact_email = Column(String(300), default="")
    referral_source = Column(String(300), default="")

    # URL liveness
    url_status = Column(String(20), default="unknown")  # alive, dead, unknown
    last_checked_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Application {self.company} - {self.job_title} ({self.status})>"

    @property
    def strengths_list(self) -> list[str]:
        if self.key_strengths:
            try:
                return json.loads(self.key_strengths)
            except json.JSONDecodeError:
                return []
        return []

    @property
    def gaps_list(self) -> list[str]:
        if self.key_gaps:
            try:
                return json.loads(self.key_gaps)
            except json.JSONDecodeError:
                return []
        return []


# Database connection management

_engine = None
_SessionLocal = None

DB_PATH = os.path.join(
    os.getenv("JOB_FINDER_DATA_DIR", os.path.join(os.getcwd(), "data")),
    "job_tracker.db",
)


def _resolved_database_url(db_path: str | None = None) -> str:
    if db_path and "://" in db_path:
        return db_path
    if db_path:
        return f"sqlite:///{db_path}"
    env_url = os.getenv("JOB_FINDER_DATABASE_URL") or os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return f"sqlite:///{DB_PATH}"


def _should_manage_schema(database_url: str) -> bool:
    env_value = os.getenv("JOB_FINDER_MANAGE_SCHEMA", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    if env_value in {"0", "false", "no", "off"}:
        return False
    return database_url.startswith("sqlite:///")


def _migrate_db(engine) -> None:
    """Add any missing columns to existing tables (lightweight migration)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "applications" not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns("applications")}
    with engine.begin() as conn:
        if "profile" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN profile VARCHAR(100) DEFAULT 'default'")
            )
        if "company_type" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN company_type VARCHAR(50) DEFAULT 'Unknown'")
            )
        if "work_type" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN work_type VARCHAR(20) DEFAULT ''")
            )
        if "url_status" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN url_status VARCHAR(20) DEFAULT 'unknown'")
            )
        if "last_checked_at" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN last_checked_at DATETIME")
            )
        if "search_run_id" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN search_run_id VARCHAR(12)")
            )
        if "workspace_id" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN workspace_id VARCHAR(64)")
            )
        if "salary_currency" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN salary_currency VARCHAR(16) DEFAULT ''")
            )
        if "salary_period" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN salary_period VARCHAR(20) DEFAULT ''")
            )
        if "salary_min_annualized" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN salary_min_annualized FLOAT")
            )
        if "salary_max_annualized" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN salary_max_annualized FLOAT")
            )
        if "evaluation_report_json" not in existing_cols:
            conn.execute(
                text("ALTER TABLE applications ADD COLUMN evaluation_report_json TEXT DEFAULT ''")
            )
        # Convert empty job_url strings to NULL (allows multiple NULLs in unique column)
        conn.execute(text("UPDATE applications SET job_url = NULL WHERE job_url = ''"))


def init_db(db_path: str | None = None) -> None:
    """Initialize the database and create tables."""
    global _engine, _SessionLocal

    database_url = _resolved_database_url(db_path)
    using_sqlite = database_url.startswith("sqlite:///")
    if using_sqlite:
        path = database_url.removeprefix("sqlite:///")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        engine_kwargs = {
            "echo": False,
            "connect_args": {"check_same_thread": False},
        }
    else:
        engine_kwargs = {
            "echo": False,
            "pool_pre_ping": True,
        }

    _engine = create_engine(database_url, **engine_kwargs)
    if _should_manage_schema(database_url):
        if using_sqlite:
            _migrate_db(_engine)
        Base.metadata.create_all(_engine)
    _SessionLocal = scoped_session(sessionmaker(bind=_engine))


def get_session() -> Session:
    """Get a database session."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


def _close_session() -> None:
    """Properly close and remove the scoped session from the registry."""
    if _SessionLocal is not None:
        _SessionLocal.remove()


def save_application(
    job_title: str,
    company: str,
    location: str = "",
    job_url: str = "",
    source: str = "",
    description: str = "",
    is_remote: bool = False,
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_currency: str = "",
    salary_period: str = "",
    salary_min_annualized: float | None = None,
    salary_max_annualized: float | None = None,
    overall_score: float | None = None,
    technical_score: float | None = None,
    leadership_score: float | None = None,
    platform_building_score: float | None = None,
    comp_potential_score: float | None = None,
    company_trajectory_score: float | None = None,
    culture_fit_score: float | None = None,
    career_progression_score: float | None = None,
    recommendation: str = "",
    score_reasoning: str = "",
    key_strengths: list[str] | str | None = None,
    key_gaps: list[str] | str | None = None,
    funding_stage: str | None = None,
    total_funding: str | None = None,
    employee_count: str | None = None,
    company_intel_json: str | None = None,
    cover_letter: str = "",
    resume_tweaks_json: str = "",
    evaluation_report_json: str = "",
    application_method: str = "",
    profile: str = "default",
    company_type: str = "Unknown",
    work_type: str = "",
    notes: str = "",
    search_run_id: str | None = None,
    workspace_id: str | None = None,
) -> ApplicationRecord | None:
    """Save a new application record to the database. Returns None if duplicate URL."""
    # Store empty URLs as None so SQLite unique constraint allows multiples
    if not job_url:
        job_url = None

    session = get_session()
    try:
        def _scope_query(query):
            if workspace_id:
                return query.filter(ApplicationRecord.workspace_id == workspace_id)
            return query.filter(ApplicationRecord.workspace_id.is_(None), ApplicationRecord.profile == profile)

        # Skip duplicates by URL — but stamp the current run_id
        if job_url:
            existing = _scope_query(
                session.query(ApplicationRecord).filter(ApplicationRecord.job_url == job_url)
            ).first()
            if existing:
                if search_run_id and existing.search_run_id != search_run_id:
                    existing.search_run_id = search_run_id
                    existing.updated_at = _utcnow()
                    session.commit()
                session.refresh(existing)
                session.expunge(existing)
                return existing

        # Skip cross-source duplicates by normalized company + title
        if job_title and company:
            from job_finder.pipeline import _normalize_company, _normalize_title
            norm_co = _normalize_company(company)
            norm_title = _normalize_title(job_title)
            if norm_co and norm_title:
                # Narrow by case-insensitive company match first (SQL-level filter)
                from sqlalchemy import func
                co_words = norm_co.split()
                # Use the longest word in the company name for SQL LIKE filter
                longest_word = max(co_words, key=len) if co_words else norm_co
                candidates = (
                    _scope_query(session.query(ApplicationRecord))
                    .filter(
                        func.lower(ApplicationRecord.company).contains(longest_word),
                        ApplicationRecord.job_title.isnot(None),
                    )
                    .all()
                )
                for cand in candidates:
                    if (
                        _normalize_company(cand.company or "") == norm_co
                        and _normalize_title(cand.job_title or "") == norm_title
                    ):
                        # Update existing record if new data is richer
                        updated = False
                        if not cand.salary_min and salary_min:
                            cand.salary_min = salary_min
                            updated = True
                        if not cand.salary_max and salary_max:
                            cand.salary_max = salary_max
                            updated = True
                        if not cand.salary_currency and salary_currency:
                            cand.salary_currency = salary_currency
                            updated = True
                        if not cand.salary_period and salary_period:
                            cand.salary_period = salary_period
                            updated = True
                        if not cand.salary_min_annualized and salary_min_annualized:
                            cand.salary_min_annualized = salary_min_annualized
                            updated = True
                        if not cand.salary_max_annualized and salary_max_annualized:
                            cand.salary_max_annualized = salary_max_annualized
                            updated = True
                        if overall_score and (not cand.overall_score or overall_score > cand.overall_score):
                            cand.overall_score = overall_score
                            cand.technical_score = technical_score
                            cand.leadership_score = leadership_score
                            cand.platform_building_score = platform_building_score
                            cand.comp_potential_score = comp_potential_score
                            cand.company_trajectory_score = company_trajectory_score
                            cand.culture_fit_score = culture_fit_score
                            cand.career_progression_score = career_progression_score
                            cand.recommendation = recommendation
                            cand.score_reasoning = score_reasoning
                            cand.key_strengths = key_strengths if isinstance(key_strengths, str) else json.dumps(key_strengths or [])
                            cand.key_gaps = key_gaps if isinstance(key_gaps, str) else json.dumps(key_gaps or [])
                            updated = True
                        if len(description) > len(cand.description or ""):
                            cand.description = description
                            updated = True
                        if cover_letter and not cand.cover_letter:
                            cand.cover_letter = cover_letter
                            updated = True
                        if company_intel_json and not cand.company_intel_json:
                            cand.company_intel_json = company_intel_json
                            updated = True
                        if resume_tweaks_json and not cand.resume_tweaks_json:
                            cand.resume_tweaks_json = resume_tweaks_json
                            updated = True
                        if evaluation_report_json and not cand.evaluation_report_json:
                            cand.evaluation_report_json = evaluation_report_json
                            updated = True
                        if search_run_id and cand.search_run_id != search_run_id:
                            cand.search_run_id = search_run_id
                            updated = True
                        if workspace_id and cand.workspace_id != workspace_id:
                            cand.workspace_id = workspace_id
                            updated = True
                        if updated:
                            cand.updated_at = _utcnow()
                            session.commit()
                        session.refresh(cand)
                        session.expunge(cand)
                        return cand

        # Normalize key_strengths/key_gaps: accept list or JSON string
        if isinstance(key_strengths, list):
            key_strengths = json.dumps(key_strengths)
        elif key_strengths is None:
            key_strengths = "[]"

        if isinstance(key_gaps, list):
            key_gaps = json.dumps(key_gaps)
        elif key_gaps is None:
            key_gaps = "[]"

        record = ApplicationRecord(
            job_title=job_title,
            company=company,
            location=location,
            job_url=job_url,
            source=source,
            description=description,
            is_remote=is_remote,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_period=salary_period,
            salary_min_annualized=salary_min_annualized,
            salary_max_annualized=salary_max_annualized,
            overall_score=overall_score,
            technical_score=technical_score,
            leadership_score=leadership_score,
            platform_building_score=platform_building_score,
            comp_potential_score=comp_potential_score,
            company_trajectory_score=company_trajectory_score,
            culture_fit_score=culture_fit_score,
            career_progression_score=career_progression_score,
            recommendation=recommendation,
            score_reasoning=score_reasoning,
            key_strengths=key_strengths,
            key_gaps=key_gaps,
            funding_stage=funding_stage,
            total_funding=total_funding,
            employee_count=employee_count,
            company_intel_json=company_intel_json or "",
            cover_letter=cover_letter,
            resume_tweaks_json=resume_tweaks_json,
            evaluation_report_json=evaluation_report_json or "",
            application_method=application_method,
            profile=profile,
            company_type=company_type,
            work_type=work_type,
            notes=notes,
            search_run_id=search_run_id,
            workspace_id=workspace_id,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        session.expunge(record)
        return record
    except Exception as exc:
        session.rollback()
        # Handle duplicate URL race condition gracefully
        if "UNIQUE constraint" in str(exc) and job_url:
            logger.debug("Duplicate job_url, returning existing: %s", job_url[:80])
            try:
                existing = session.query(ApplicationRecord).filter_by(job_url=job_url).first()
                if existing:
                    session.refresh(existing)
                    session.expunge(existing)
                    return existing
            except Exception:
                pass
            return None
        raise
    finally:
        _close_session()


def update_application_status(
    application_id: int,
    status: str,
    notes: str | None = None,
) -> ApplicationRecord | None:
    """Update the status of an application."""
    session = get_session()
    try:
        record = session.query(ApplicationRecord).filter_by(id=application_id).first()
        if record:
            record.status = status
            record.updated_at = _utcnow()
            if status == "applied":
                record.date_applied = _utcnow()
            if notes:
                existing = record.notes or ""
                timestamp = _utcnow().strftime("%Y-%m-%d %H:%M")
                record.notes = f"{existing}\n[{timestamp}] {notes}".strip()
            session.commit()
            session.refresh(record)
            session.expunge(record)
        return record
    except Exception:
        session.rollback()
        raise
    finally:
        _close_session()


def get_all_applications(
    status: str | None = None,
    min_score: float | None = None,
    profile: str | None = None,
    company_type: str | None = None,
    workspace_id: str | None = None,
) -> list[ApplicationRecord]:
    """Retrieve applications with optional filters."""
    session = get_session()
    try:
        query = session.query(ApplicationRecord)
        if profile:
            query = query.filter(ApplicationRecord.profile == profile)
        if workspace_id:
            query = query.filter(ApplicationRecord.workspace_id == workspace_id)
        if status:
            query = query.filter(ApplicationRecord.status == status)
        if min_score is not None:
            query = query.filter(ApplicationRecord.overall_score >= min_score)
        if company_type:
            query = query.filter(ApplicationRecord.company_type == company_type)
        results = query.order_by(ApplicationRecord.overall_score.desc()).all()
        session.expunge_all()
        return results
    finally:
        _close_session()


def purge_non_matching_locations(
    preferred_states: list[str] | None = None,
    preferred_cities: list[str] | None = None,
    preferred_locations: list[str] | None = None,
    preferred_places: list[dict] | None = None,
    include_remote: bool = True,
    remote_only: bool = False,
    profile: str | None = None,
    workspace_id: str | None = None,
) -> int:
    """Delete existing records that don't match location preferences.

    Remote jobs are always kept. When ``profile`` is provided, only records
    for that profile are considered. Returns the number of deleted records.
    """
    if not preferred_states and not preferred_cities and not preferred_locations and not preferred_places and include_remote and not remote_only:
        return 0

    from job_finder.company_classifier import (
        classify_work_type,
        location_matches_preferences,
    )

    session = get_session()
    try:
        query = session.query(ApplicationRecord)
        if profile:
            query = query.filter(ApplicationRecord.profile == profile)
        if workspace_id:
            query = query.filter(ApplicationRecord.workspace_id == workspace_id)
        records = query.all()
        deleted = 0
        for rec in records:
            # Use stored work_type when available; otherwise re-classify
            # from location + description to avoid stale is_remote flags.
            wt = rec.work_type or classify_work_type(
                rec.location or "",
                rec.description or "",
                rec.is_remote or False,
            )
            if not location_matches_preferences(
                rec.location or "",
                rec.is_remote or False,
                preferred_states,
                preferred_cities,
                preferred_locations,
                remote_only=remote_only,
                include_remote=include_remote,
                work_type=wt,
                preferred_places=preferred_places,
            ):
                session.delete(rec)
                deleted += 1
        session.commit()
        return deleted
    except Exception:
        session.rollback()
        raise
    finally:
        _close_session()


def purge_non_matching_roles(
    target_roles: list[str],
    profile: str | None = None,
    workspace_id: str | None = None,
) -> int:
    """Delete existing records whose titles don't match any target role.

    Uses the same ``_match_roles()`` logic as the scrapers so filtering is
    consistent between new searches and existing DB records.
    Returns the number of deleted records.
    """
    if not target_roles:
        return 0

    from job_finder.tools.scrapers._utils import _match_roles

    session = get_session()
    try:
        query = session.query(ApplicationRecord)
        if profile:
            query = query.filter(ApplicationRecord.profile == profile)
        if workspace_id:
            query = query.filter(ApplicationRecord.workspace_id == workspace_id)
        records = query.all()
        deleted = 0
        for rec in records:
            if not _match_roles(rec.job_title or "", target_roles):
                session.delete(rec)
                deleted += 1
        session.commit()
        return deleted
    except Exception:
        session.rollback()
        raise
    finally:
        _close_session()


def backfill_company_types() -> int:
    """Classify existing records that have company_type='Unknown' or NULL."""
    from job_finder.company_classifier import classify_company

    session = get_session()
    try:
        records = session.query(ApplicationRecord).filter(
            (ApplicationRecord.company_type == "Unknown")
            | (ApplicationRecord.company_type == None)  # noqa: E711
        ).all()
        updated = 0
        for rec in records:
            ct = classify_company(
                rec.company or "",
                rec.funding_stage,
                rec.total_funding,
                rec.employee_count,
            )
            if ct != "Unknown":
                rec.company_type = ct
                updated += 1
        session.commit()
        return updated
    except Exception:
        session.rollback()
        raise
    finally:
        _close_session()


def backfill_scores(
    profile: str | None = None,
    progress: Callable[[str], None] | None = None,
    workspace_id: str | None = None,
) -> int:
    """Score all DB records that have NULL overall_score.

    Uses keyword-based scoring (no LLM required). Loads the resume once
    and scores each unscored record against it. Records that fail to score
    are skipped so one bad record does not block the rest.

    Returns the number of records successfully scored.
    """
    from job_finder.scoring import score_job_basic
    from job_finder.tools.resume_parser_tool import parse_resume
    from job_finder.pipeline import _load_search_config

    config = _load_search_config(profile)

    # Load resume text once for all scoring
    resume_text = parse_resume("", profile=profile or "default")
    if not resume_text:
        logger.warning("backfill_scores: no resume found for profile=%s", profile)
        if progress:
            progress("No resume found — cannot score jobs")
        return 0

    session = get_session()
    try:
        query = session.query(ApplicationRecord).filter(
            ApplicationRecord.overall_score == None  # noqa: E711
        )
        if profile:
            query = query.filter(ApplicationRecord.profile == profile)
        if workspace_id:
            query = query.filter(ApplicationRecord.workspace_id == workspace_id)
        records = query.all()

        if not records:
            if progress:
                progress("No unscored records found")
            return 0

        if progress:
            progress(f"Backfilling scores for {len(records)} unscored jobs...")

        scored = 0
        for i, rec in enumerate(records, 1):
            try:
                score_data = score_job_basic(
                    job_description=rec.description or "",
                    resume_text=resume_text,
                    job_title=rec.job_title or "",
                    company=rec.company or "",
                    company_type=rec.company_type or "Unknown",
                    salary_min=rec.salary_min,
                    salary_max=rec.salary_max,
                    salary_period=rec.salary_period or "",
                    is_remote=rec.is_remote or False,
                    config=config,
                )

                rec.overall_score = score_data["overall_score"]
                rec.technical_score = score_data["technical_score"]
                rec.leadership_score = score_data["leadership_score"]
                rec.platform_building_score = score_data["platform_building_score"]
                rec.comp_potential_score = score_data["comp_potential_score"]
                rec.company_trajectory_score = score_data["company_trajectory_score"]
                rec.culture_fit_score = score_data["culture_fit_score"]
                rec.career_progression_score = score_data["career_progression_score"]
                rec.recommendation = score_data["recommendation"]
                rec.score_reasoning = score_data.get("score_reasoning", "")
                rec.key_strengths = json.dumps(score_data.get("key_strengths", []))
                rec.key_gaps = json.dumps(score_data.get("key_gaps", []))
                rec.updated_at = _utcnow()
                scored += 1

                if progress and (i % 10 == 0 or i == len(records)):
                    progress(f"Scored {i}/{len(records)} jobs")
            except Exception:
                logger.warning(
                    "backfill_scores: failed to score record id=%s (%s @ %s)",
                    rec.id, rec.job_title, rec.company,
                    exc_info=True,
                )
                continue

        session.commit()

        if progress:
            progress(f"Backfill complete — scored {scored} jobs")

        return scored
    except Exception:
        session.rollback()
        raise
    finally:
        _close_session()
