"""Schedule API — CRUD for recurring search schedules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.schedule import Schedule
from app.schemas.schedule import ScheduleResponse, ScheduleUpdate

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("", response_model=ScheduleResponse)
def get_schedule(
    profile: str = "default", db: Session = Depends(get_db)
) -> ScheduleResponse:
    """Get the schedule for a profile (returns defaults if none exists)."""
    sched = db.query(Schedule).filter(Schedule.profile == profile).first()
    if not sched:
        return ScheduleResponse(profile=profile)
    return ScheduleResponse.model_validate(sched)


@router.put("", response_model=ScheduleResponse)
def update_schedule(
    body: ScheduleUpdate,
    profile: str = "default",
    db: Session = Depends(get_db),
) -> ScheduleResponse:
    """Create or update the schedule for a profile."""
    sched = db.query(Schedule).filter(Schedule.profile == profile).first()
    if not sched:
        sched = Schedule(profile=profile)
        db.add(sched)

    sched.enabled = body.enabled
    sched.interval_hours = body.interval_hours
    sched.mode = body.mode

    # Set next_run_at when enabling; clear when disabling
    now = _utcnow()
    if body.enabled:
        if not sched.next_run_at or sched.next_run_at < now:
            sched.next_run_at = now + timedelta(hours=body.interval_hours)
    else:
        sched.next_run_at = None

    sched.updated_at = now
    db.commit()
    db.refresh(sched)
    return ScheduleResponse.model_validate(sched)
