from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.application import ApplicationRecord

_ALLOWED_SORT_BY = frozenset({
    "overall_score", "date_found", "company", "job_title", "salary_min", "salary_max",
})


def _utcnow():
    return datetime.now(timezone.utc)


def get_applications(
    db: Session,
    *,
    status: str | None = None,
    min_score: float | None = None,
    recommendation: str | None = None,
    source: str | None = None,
    search: str | None = None,
    company_type: str | None = None,
    is_remote: bool | None = None,
    work_type: str | None = None,
    profile: str | None = None,
    search_run_id: str | None = None,
    sort_by: str = "overall_score",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[ApplicationRecord], int]:
    if sort_by not in _ALLOWED_SORT_BY:
        sort_by = "overall_score"
    query = db.query(ApplicationRecord)

    if status:
        query = query.filter(ApplicationRecord.status == status)
    if min_score is not None:
        query = query.filter(ApplicationRecord.overall_score >= min_score)
    if recommendation:
        query = query.filter(ApplicationRecord.recommendation == recommendation)
    if source:
        query = query.filter(ApplicationRecord.source == source)
    if company_type:
        query = query.filter(ApplicationRecord.company_type == company_type)
    if is_remote is not None:
        query = query.filter(ApplicationRecord.is_remote == is_remote)
    if work_type:
        query = query.filter(ApplicationRecord.work_type == work_type)
    if profile:
        query = query.filter(ApplicationRecord.profile == profile)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                ApplicationRecord.job_title.ilike(pattern),
                ApplicationRecord.company.ilike(pattern),
                ApplicationRecord.description.ilike(pattern),
            )
        )

    total = query.count()

    # Sorting
    sort_col = getattr(ApplicationRecord, sort_by, ApplicationRecord.overall_score)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc().nullslast())
    else:
        query = query.order_by(sort_col.desc().nullsfirst())

    # Pagination
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()

    return items, total


def get_application(db: Session, app_id: int) -> ApplicationRecord | None:
    return db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id).first()


def create_application(db: Session, data) -> ApplicationRecord:
    """Create a new application record from an ApplicationCreate schema."""
    record = ApplicationRecord(
        job_title=data.job_title,
        company=data.company,
        location=data.location,
        job_url=data.job_url,
        source=data.source,
        description=data.description,
        is_remote=data.is_remote,
        salary_min=data.salary_min,
        salary_max=data.salary_max,
        status=data.status,
        notes=data.notes,
        profile=data.profile,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_application(
    db: Session, app_id: int, **kwargs
) -> ApplicationRecord | None:
    record = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id).first()
    if not record:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(record, key):
            setattr(record, key, value)
    record.updated_at = _utcnow()
    if kwargs.get("status") == "applied" and not record.date_applied:
        record.date_applied = _utcnow()
    db.commit()
    db.refresh(record)
    return record


def check_urls(db: Session, ids: list[int] | None = None, limit: int = 100) -> dict:
    """HEAD-check job URLs and update url_status. Returns summary counts."""
    import requests as req

    query = db.query(ApplicationRecord).filter(ApplicationRecord.job_url.isnot(None))
    if ids:
        query = query.filter(ApplicationRecord.id.in_(ids))
    else:
        # Check oldest-checked first, or never-checked
        query = query.order_by(ApplicationRecord.last_checked_at.asc().nullsfirst())
    records = query.limit(limit).all()

    alive, dead, errors = 0, 0, 0
    for rec in records:
        try:
            r = req.head(rec.job_url, timeout=8, allow_redirects=True)
            if r.status_code < 400:
                rec.url_status = "alive"
                alive += 1
            else:
                rec.url_status = "dead"
                dead += 1
        except Exception:
            rec.url_status = "dead"
            errors += 1
        rec.last_checked_at = _utcnow()

    db.commit()
    return {"checked": len(records), "alive": alive, "dead": dead + errors}


def delete_application(db: Session, app_id: int) -> bool:
    record = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id).first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True
