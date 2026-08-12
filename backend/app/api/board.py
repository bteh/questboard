"""Board summary: live supply per quest kind, for the board rail.

The kinds come from packages/kinds/kinds.json via job_finder.kinds; stored
rows keep their historical vertical values and are mapped at read time, so
no migration and no scraper edits. Kinds with zero supply are still
returned: supply honesty (a thin kind says so) is the client's call to make.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.dependencies import get_active_workspace_context, workspace_scope_id
from app.models.database import get_db
from app.schemas.board import BoardSummaryResponse, CareerRefreshReceipt, KindSummary
from app.models.workspace import WorkspaceSearchRun
from app.services import workspace_service

from app.services.application_service import (
    board_filter_conditions,
    found_window_condition,
    publishable_source_condition,
    time_sensitive_stale,
)
from job_finder.kinds import get_kinds, kind_for_vertical
from job_finder.models.database import ApplicationRecord, ScrapeRunRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/board", tags=["board"])


@router.get("/summary", response_model=BoardSummaryResponse)
def board_summary(
    profile: str | None = None,
    search: str | None = Query(None, max_length=120),
    location: str | None = Query(
        None,
        max_length=120,
        description="Place text; same reachability rules as the /applications list",
    ),
    location_strict: bool = Query(
        False,
        description='"Near me only": with a location set, keeps only rows that match the place',
    ),
    salary_min: float | None = Query(None, ge=0, description="Annual pay floor; keeps rows with no pay data"),
    salary_max: float | None = Query(None, ge=0, description="Annual pay ceiling; keeps rows with no pay data"),
    salary_currency: str | None = Query(
        None,
        min_length=3,
        max_length=8,
        description="Currency of the pay bounds; unlike or unstated currencies remain eligible",
    ),
    is_remote: bool | None = None,
    first_quest_ok: bool | None = None,
    posted_within_days: int | None = Query(None, ge=1),
    found_within_days: int | None = Query(None, ge=1, le=365),
    timezone_name: str = "UTC",
    workspace = Depends(get_active_workspace_context),
    db: Session = Depends(get_db),
):
    """Counts per kind plus how many genuinely arrived today.

    Takes the board's own filter params and applies them through the shared
    service predicates, so the rail's badges and the "All quests" total
    always agree with the filtered list they sit above.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    new_today = found_window_condition(
        ApplicationRecord,
        1,
        timezone_name,
    )

    query = (
        db.query(
            ApplicationRecord.vertical,
            func.count(ApplicationRecord.id),
            func.sum(
                case((new_today, 1), else_=0)
            ),
        )
        .filter(ApplicationRecord.vertical != "personal")
        .filter(publishable_source_condition(ApplicationRecord))
        # dead = the link 404s; expired = the source stopped listing it
        # (job_finder.expiry). Both are tombstones, both stay off the board.
        .filter(ApplicationRecord.url_status.notin_(("dead", "expired")))
        # same upcoming semantics as the board list: a taping that already
        # happened is off the board, rows with no event date pass
        .filter(
            or_(
                ApplicationRecord.event_start.is_(None),
                ApplicationRecord.event_start >= now,
            )
        )
        # casting/audition calls carry their date only in the text; drop the
        # ones whose publish date is past the shelf life so counts match the list
        .filter(~time_sensitive_stale(ApplicationRecord))
    )
    # the user's own filters, via the same predicates the list applies,
    # never re-derived here, so the two surfaces cannot drift apart
    for condition in board_filter_conditions(
        ApplicationRecord,
        search=search,
        location=location,
        location_strict=location_strict,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        is_remote=is_remote,
        first_quest_ok=first_quest_ok,
        posted_within_days=posted_within_days,
        found_within_days=found_within_days,
        timezone_name=timezone_name,
    ):
        query = query.filter(condition)
    scope = workspace_scope_id(workspace)
    if scope:
        # hosted: the shared quest pool plus this workspace's own rows
        from app.services.row_scope import visible_rows_filter

        query = query.filter(visible_rows_filter(scope))
    elif profile:
        query = query.filter(ApplicationRecord.profile == profile)
    rows = query.group_by(ApplicationRecord.vertical).all()

    counts: dict[str, int] = {}
    fresh: dict[str, int] = {}
    for vertical, count, new_today in rows:
        kind = kind_for_vertical(vertical or "career")
        if kind is None:
            logger.warning("board summary: row with unknown vertical %r skipped", vertical)
            continue
        counts[kind.id] = counts.get(kind.id, 0) + int(count or 0)
        fresh[kind.id] = fresh.get(kind.id, 0) + int(new_today or 0)

    kinds = [
        KindSummary(
            id=kind.id,
            label=kind.label,
            sub=kind.sub,
            hue=kind.hue,
            order=kind.order,
            count=counts.get(kind.id, 0),
            new_today=fresh.get(kind.id, 0),
        )
        for kind in get_kinds()
    ]
    # Side-quest sources run on independent cadences, so their freshness comes
    # from the newest healthy non-career source attempt.
    side_quest_checked_at = (
        db.query(func.max(ScrapeRunRecord.started_at))
        .filter(
            ScrapeRunRecord.vertical != "career",
            ScrapeRunRecord.finish_reason == "ok",
            ScrapeRunRecord.rows_found > 0,
        )
        .scalar()
    )

    # Find Work must only say it was checked after the WHOLE durable pull
    # completed. Individual source logs can land while other sources are still
    # running (or before an interrupted run saves anything), so using their
    # latest timestamp made a partial pull look fresh.
    career_query = db.query(func.max(WorkspaceSearchRun.completed_at)).filter(
        WorkspaceSearchRun.status == "completed",
    )
    if workspace:
        career_query = career_query.filter(
            WorkspaceSearchRun.workspace_id == workspace.workspace.id,
        )
    career_checked_at = career_query.scalar()

    latest_run_query = db.query(WorkspaceSearchRun)
    if workspace:
        latest_run_query = latest_run_query.filter(
            WorkspaceSearchRun.workspace_id == workspace.workspace.id,
        )
    latest_run = latest_run_query.order_by(WorkspaceSearchRun.created_at.desc()).first()
    career_refresh = None
    if latest_run is not None:
        result_payload = workspace_service.get_search_result(
            db,
            latest_run.workspace_id,
            latest_run.run_id,
        )
        career_refresh = CareerRefreshReceipt(
            run_id=latest_run.run_id,
            status=latest_run.status or "pending",
            started_at=latest_run.started_at,
            completed_at=latest_run.completed_at,
            jobs_found=int(latest_run.jobs_found or result_payload.get("jobs_found") or 0),
            new_jobs=int(result_payload.get("new_jobs") or 0),
            error=latest_run.error or None,
            source_coverage=result_payload.get("source_coverage") or None,
        )
    completed_times = [
        value for value in (career_checked_at, side_quest_checked_at) if value is not None
    ]
    checked_at = max(completed_times) if completed_times else None

    return BoardSummaryResponse(
        total=sum(counts.values()),
        new_today=sum(fresh.values()),
        checked_at=checked_at,
        career_checked_at=career_checked_at,
        side_quest_checked_at=side_quest_checked_at,
        career_refresh=career_refresh,
        kinds=kinds,
    )
