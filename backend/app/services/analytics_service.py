from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.application import ApplicationRecord


def get_dashboard_stats(db: Session) -> dict:
    total = db.query(func.count(ApplicationRecord.id)).scalar() or 0
    avg_score = db.query(func.avg(ApplicationRecord.overall_score)).scalar()

    def count_rec(rec):
        return db.query(func.count(ApplicationRecord.id)).filter(
            ApplicationRecord.recommendation == rec
        ).scalar() or 0

    def count_status(st):
        return db.query(func.count(ApplicationRecord.id)).filter(
            ApplicationRecord.status == st
        ).scalar() or 0

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


def get_score_distribution(db: Session) -> list[dict]:
    results = []
    ranges = [(0, 20), (20, 40), (40, 55), (55, 70), (70, 100)]
    labels = ["0-20", "20-40", "40-55", "55-70", "70-100"]
    colors = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#10b981"]
    for (lo, hi), label, color in zip(ranges, labels, colors):
        count = db.query(func.count(ApplicationRecord.id)).filter(
            ApplicationRecord.overall_score >= lo,
            ApplicationRecord.overall_score < hi,
        ).scalar() or 0
        results.append({"label": label, "value": count, "color": color})
    return results


def get_recommendation_breakdown(db: Session) -> list[dict]:
    recs = [
        ("STRONG_APPLY", "#10b981"),
        ("APPLY", "#3b82f6"),
        ("MAYBE", "#eab308"),
        ("SKIP", "#6b7280"),
    ]
    results = []
    for rec, color in recs:
        count = db.query(func.count(ApplicationRecord.id)).filter(
            ApplicationRecord.recommendation == rec
        ).scalar() or 0
        results.append({"label": rec, "value": count, "color": color})
    return results


def get_source_breakdown(db: Session) -> list[dict]:
    rows = (
        db.query(ApplicationRecord.source, func.count(ApplicationRecord.id))
        .group_by(ApplicationRecord.source)
        .order_by(func.count(ApplicationRecord.id).desc())
        .limit(10)
        .all()
    )
    return [{"label": source or "Unknown", "value": count, "color": None} for source, count in rows]


def get_pipeline_funnel(db: Session) -> list[dict]:
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
        count = db.query(func.count(ApplicationRecord.id)).filter(
            ApplicationRecord.status == status
        ).scalar() or 0
        results.append({"label": status, "value": count, "color": color})
    return results


def get_top_companies(db: Session, limit: int = 10) -> list[dict]:
    """Top N companies by average overall score."""
    rows = (
        db.query(
            ApplicationRecord.company,
            func.avg(ApplicationRecord.overall_score).label("avg_score"),
            func.count(ApplicationRecord.id).label("job_count"),
        )
        .filter(ApplicationRecord.overall_score.isnot(None))
        .group_by(ApplicationRecord.company)
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


def get_company_types(db: Session) -> list[dict]:
    """Jobs grouped by company type classification."""
    rows = (
        db.query(
            ApplicationRecord.company_type,
            func.count(ApplicationRecord.id).label("count"),
            func.avg(ApplicationRecord.overall_score).label("avg_score"),
        )
        .group_by(ApplicationRecord.company_type)
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
