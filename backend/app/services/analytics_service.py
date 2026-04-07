from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.application import ApplicationRecord


def _base_query(
    db: Session,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
):
    """Return a base query, optionally filtered by profile."""
    q = db.query(ApplicationRecord)
    if workspace_id:
        q = q.filter(ApplicationRecord.workspace_id == workspace_id)
    elif profile:
        q = q.filter(ApplicationRecord.profile == profile)
    if search_run_id:
        q = q.filter(ApplicationRecord.search_run_id == search_run_id)
    return q


def get_dashboard_stats(
    db: Session,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> dict:
    base = _base_query(db, profile, workspace_id, search_run_id)
    total = base.count()
    avg_score = base.with_entities(func.avg(ApplicationRecord.overall_score)).scalar()

    def count_rec(rec):
        return base.filter(ApplicationRecord.recommendation == rec).count()

    def count_status(st):
        return base.filter(ApplicationRecord.status == st).count()

    applied = count_status("applied")
    interviewing = count_status("interviewing")
    offer = count_status("offer")

    response_rate = 0.0
    if applied > 0:
        response_rate = (interviewing + offer) / applied * 100

    return {
        "total_jobs": total,
        "avg_score": round(avg_score, 1) if avg_score else None,
        "strong_apply_count": count_rec("STRONG_APPLY"),
        "apply_count": count_rec("APPLY"),
        "maybe_count": count_rec("MAYBE"),
        "skip_count": count_rec("SKIP"),
        "applied_count": applied,
        "interviewing_count": interviewing,
        "offer_count": offer,
        "response_rate": round(response_rate, 1),
    }


def get_score_distribution(
    db: Session,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> list[dict]:
    base = _base_query(db, profile, workspace_id, search_run_id)
    results = []
    ranges = [(0, 20), (20, 40), (40, 55), (55, 70), (70, 100)]
    labels = ["0-20", "20-40", "40-55", "55-70", "70-100"]
    colors = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#10b981"]
    for (lo, hi), label, color in zip(ranges, labels, colors):
        count = base.filter(
            ApplicationRecord.overall_score >= lo,
            ApplicationRecord.overall_score < hi,
        ).count()
        results.append({"label": label, "value": count, "color": color})
    return results


def get_recommendation_breakdown(
    db: Session,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> list[dict]:
    base = _base_query(db, profile, workspace_id, search_run_id)
    recs = [
        ("STRONG_APPLY", "#10b981"),
        ("APPLY", "#3b82f6"),
        ("MAYBE", "#eab308"),
        ("SKIP", "#6b7280"),
    ]
    results = []
    for rec, color in recs:
        count = base.filter(ApplicationRecord.recommendation == rec).count()
        results.append({"label": rec, "value": count, "color": color})
    return results


def get_source_breakdown(
    db: Session,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> list[dict]:
    base = _base_query(db, profile, workspace_id, search_run_id)
    rows = (
        base.with_entities(ApplicationRecord.source, func.count(ApplicationRecord.id))
        .group_by(ApplicationRecord.source)
        .order_by(func.count(ApplicationRecord.id).desc())
        .limit(10)
        .all()
    )
    return [{"label": source or "Unknown", "value": count, "color": None} for source, count in rows]


def get_pipeline_funnel(
    db: Session,
    profile: str | None = None,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> list[dict]:
    base = _base_query(db, profile, workspace_id, search_run_id)
    statuses = [
        ("found", "#6b7280"),
        ("reviewed", "#3b82f6"),
        ("applying", "#eab308"),
        ("applied", "#22c55e"),
        ("interviewing", "#f59e0b"),
        ("offer", "#10b981"),
    ]
    results = []
    for status, color in statuses:
        count = base.filter(ApplicationRecord.status == status).count()
        results.append({"label": status, "value": count, "color": color})
    return results


def get_top_companies(
    db: Session,
    limit: int = 10,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> list[dict]:
    """Top N companies by average overall score."""
    query = db.query(
        ApplicationRecord.company,
        func.avg(ApplicationRecord.overall_score).label("avg_score"),
        func.count(ApplicationRecord.id).label("job_count"),
    ).filter(ApplicationRecord.overall_score.isnot(None))
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    rows = (
        query.group_by(ApplicationRecord.company)
        .order_by(func.avg(ApplicationRecord.overall_score).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "company": row.company,
            "avg_score": round(row.avg_score, 1) if row.avg_score else 0,
            "job_count": row.job_count,
        }
        for row in rows
    ]


def get_company_types(
    db: Session,
    workspace_id: str | None = None,
    search_run_id: str | None = None,
) -> list[dict]:
    """Jobs grouped by company type classification."""
    query = db.query(
        ApplicationRecord.company_type,
        func.count(ApplicationRecord.id).label("count"),
        func.avg(ApplicationRecord.overall_score).label("avg_score"),
    )
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    rows = (
        query.group_by(ApplicationRecord.company_type)
        .order_by(func.count(ApplicationRecord.id).desc())
        .all()
    )
    return [
        {
            "company_type": row.company_type or "Unknown",
            "count": row.count,
            "avg_score": round(row.avg_score, 1) if row.avg_score else None,
        }
        for row in rows
    ]
