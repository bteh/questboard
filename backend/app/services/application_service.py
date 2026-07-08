from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

# The mandatory vertical scope. Every list-level read of applications goes
# through it so quest rows never leak into career surfaces by omission.
from job_finder.models.database import scoped_applications
from app.models.application import ApplicationRecord

_ALLOWED_SORT_BY = frozenset({
    "overall_score", "date_found", "company", "job_title", "salary_min", "salary_max",
    "event_start",
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
    salary_min: float | None = None,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
    first_seen_run_id: str | None = None,
    exclude_dead: bool = False,
    upcoming_only: bool = False,
    sort_by: str = "overall_score",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 25,
    verticals: list[str] | None = None,
) -> tuple[list[ApplicationRecord], int]:
    if sort_by not in _ALLOWED_SORT_BY:
        sort_by = "overall_score"
    # Career by default: the classic page and its counts never see quest rows
    # (which are unscored and would float to the top of the default
    # overall_score desc nullsfirst sort) unless a caller opts in.
    query = scoped_applications(db.query(ApplicationRecord), verticals)

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
    if salary_min is not None:
        # Annual pay floor. Mirrors job_finder.pipeline._job_salary_passes:
        # prefer annualized values, use the range midpoint when both ends are
        # stated, and KEEP rows with no salary data (dropping them would hide
        # most listings, and "no pay stated" is not "pays below the floor").
        lo = func.coalesce(
            ApplicationRecord.salary_min_annualized, ApplicationRecord.salary_min
        )
        hi = func.coalesce(
            ApplicationRecord.salary_max_annualized, ApplicationRecord.salary_max
        )
        query = query.filter(
            or_(
                and_(lo.is_(None), hi.is_(None)),
                and_(lo.isnot(None), hi.isnot(None), (lo + hi) / 2 >= salary_min),
                and_(lo.is_(None), hi.isnot(None), hi >= salary_min),
                and_(lo.isnot(None), hi.is_(None), lo >= salary_min),
            )
        )
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    elif profile:
        query = query.filter(ApplicationRecord.profile == profile)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    if first_seen_run_id:
        query = query.filter(ApplicationRecord.first_seen_run_id == first_seen_run_id)
    if exclude_dead:
        # Hide only CONFIRMED-dead postings; unknown/alive/never-checked stay.
        query = query.filter(ApplicationRecord.url_status != "dead")
    if upcoming_only:
        # Drop quests whose taping/session already happened. NULL event_start
        # (career rows, rolling signups) always passes: "no date" is not
        # "in the past". Stored values are naive UTC, so compare naive UTC.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = query.filter(
            or_(
                ApplicationRecord.event_start.is_(None),
                ApplicationRecord.event_start >= now,
            )
        )
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


def get_application(db: Session, app_id: int, workspace_id: str | None = None) -> ApplicationRecord | None:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    return query.first()


def create_application(db: Session, data, workspace_id: str | None = None) -> ApplicationRecord:
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
        workspace_id=workspace_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_application(
    db: Session, app_id: int, workspace_id: str | None = None, **kwargs
) -> ApplicationRecord | None:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    record = query.first()
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


def check_urls(
    db: Session,
    ids: list[int] | None = None,
    limit: int = 100,
    workspace_id: str | None = None,
) -> dict:
    """HEAD-check job URLs and update url_status. Returns summary counts."""
    import requests as req

    query = db.query(ApplicationRecord).filter(ApplicationRecord.job_url.isnot(None))
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    if ids:
        query = query.filter(ApplicationRecord.id.in_(ids))
    else:
        # Check oldest-checked first, or never-checked
        query = query.order_by(ApplicationRecord.last_checked_at.asc().nullsfirst())
    records = query.limit(limit).all()

    # Classify ONE url. Only a definitive 404/410 means the posting is gone.
    # 403/405/429/5xx are usually bot-blocks or HEAD-not-supported, and
    # timeouts/connection errors are transient — none of those should mark a
    # live job dead (that would hide good postings). Those map to "unknown".
    def _classify(url: str) -> str:
        try:
            r = req.head(url, timeout=8, allow_redirects=True)
            code = r.status_code
            if code < 400:
                return "alive"
            if code in (404, 410):
                return "dead"
            return "unknown"
        except Exception:
            return "unknown"

    now = _utcnow()
    statuses: dict[int, str] = {}
    if records:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(records), 8)) as pool:
            for rec, status in zip(records, pool.map(lambda r: _classify(r.job_url), records)):
                statuses[rec.id] = status

    alive = dead = unknown = 0
    for rec in records:
        status = statuses.get(rec.id, "unknown")
        rec.url_status = status
        rec.last_checked_at = now
        if status == "alive":
            alive += 1
        elif status == "dead":
            dead += 1
        else:
            unknown += 1

    db.commit()
    return {"checked": len(records), "alive": alive, "dead": dead, "unknown": unknown}


def delete_application(db: Session, app_id: int, workspace_id: str | None = None) -> bool:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    record = query.first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True
