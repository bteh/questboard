from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

# The mandatory vertical scope. Every list-level read of applications goes
# through it so quest rows never leak into career surfaces by omission.
from job_finder.models.database import APPLICATION_VERTICALS, scoped_applications
from app.models.application import ApplicationRecord

_ALLOWED_SORT_BY = frozenset({
    "overall_score", "date_found", "company", "job_title", "salary_min", "salary_max",
    "event_start", "updated_at",
})


def _utcnow():
    return datetime.now(timezone.utc)


# Casting / audition quests are short-lived, and their real audition date lives
# only in the posting text (e.g. "auditions JUNE 15"), so event_start is NULL
# and the upcoming-only filter can't expire them. Once the source's publish date
# is older than this shelf life, the call has almost certainly passed. Only ISO
# date_posted strings sort below the cutoff, so free-text ("Reposted 9 days ago")
# and absent dates are conservatively KEPT on the board.
TIME_SENSITIVE_VERTICALS = ("camera",)
TIME_SENSITIVE_SHELF_DAYS = 30


def time_sensitive_stale(model, now: datetime | None = None):
    """A SQLAlchemy condition that is TRUE for a stale time-sensitive quest.

    Negate with ``~`` to keep everything else. ``model`` is the caller's
    ApplicationRecord class (board_summary imports a different one), so the
    filter binds to that module's mapped columns.
    """
    ref = now or datetime.now(timezone.utc)
    cutoff = (ref - timedelta(days=TIME_SENSITIVE_SHELF_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    return and_(
        model.vertical.in_(TIME_SENSITIVE_VERTICALS),
        model.event_start.is_(None),
        # Only a real ISO date_posted expires. The >= "2000-01-01" floor drops
        # empty strings and free text ("Reposted 9 days ago"), which sort below
        # a real year and would otherwise look "older than the cutoff".
        model.date_posted >= "2000-01-01",
        model.date_posted < cutoff,
    )


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
    location: str | None = None,
    location_strict: bool = False,
    salary_min: float | None = None,
    profile: str | None = None,
    workspace_id: str | None = None,
    shared_quest_workspace: str | None = None,
    search_run_id: str | None = None,
    first_seen_run_id: str | None = None,
    exclude_dead: bool = False,
    upcoming_only: bool = False,
    first_quest_ok: bool | None = None,
    posted_within_days: int | None = None,
    event_within_days: int | None = None,
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
        # Single value or comma list, mirroring the vertical param: the log
        # reads its whole spread (clipped, applied, shelved, done...) in one
        # query so every surface shares one cache entry.
        wanted_statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(wanted_statuses) == 1:
            query = query.filter(ApplicationRecord.status == wanted_statuses[0])
        elif wanted_statuses:
            query = query.filter(ApplicationRecord.status.in_(wanted_statuses))
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
    if location:
        # A place filter narrows to quests you can actually reach; it must
        # never hide work-from-anywhere. Rows pass when their location
        # matches, when they say remote/online/nationwide in any wording,
        # or when the source stated no place at all (unknown is not
        # "elsewhere"). A typed US state (either spelling) matches the
        # pre-parsed state_codes token field, so "Georgia" and "GA" both
        # find a "VA, GA & NC only" bonus and neither matches
        # "Guadalajara" or "West Virginia" (job_finder.us_states explains
        # why this beats tokenizing prose in SQL). A typed city or free
        # text keeps a plain location substring match.
        from job_finder.us_states import state_aliases

        aliases = state_aliases(location)
        if aliases:
            _full_name, abbr = aliases
            place_match = ApplicationRecord.state_codes.like(f"%,{abbr},%")
        else:
            place_match = ApplicationRecord.location.ilike(f"%{location.strip()}%")
        if location_strict:
            # "near me only": keep only rows that actually match the place, so
            # the filter visibly bites. Remote and placeless supply drop.
            query = query.filter(place_match)
        else:
            query = query.filter(
                or_(
                    place_match,
                    ApplicationRecord.location.is_(None),
                    ApplicationRecord.location == "",
                    ApplicationRecord.location.ilike("%remote%"),
                    ApplicationRecord.location.ilike("%online%"),
                    ApplicationRecord.location.ilike("%nationwide%"),
                    ApplicationRecord.location.ilike("%anywhere%"),
                    ApplicationRecord.is_remote.is_(True),
                )
            )
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
    if shared_quest_workspace:
        # hosted board read: your rows plus the shared quest pool
        # (see app.services.row_scope for the visibility contract)
        from app.services.row_scope import visible_rows_filter

        query = query.filter(visible_rows_filter(shared_quest_workspace))
    elif workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    elif profile:
        query = query.filter(ApplicationRecord.profile == profile)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    if first_seen_run_id:
        query = query.filter(ApplicationRecord.first_seen_run_id == first_seen_run_id)
    if exclude_dead:
        # Hide only CONFIRMED-dead postings; unknown/alive/never-checked stay.
        # expired rows (source stopped listing them) hide with the dead ones;
        # include_dead=true still surfaces both tombstone shapes
        query = query.filter(ApplicationRecord.url_status.notin_(("dead", "expired")))
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
        # Casting calls carry their date only in the text, so also drop the
        # ones whose publish date is past the shelf life.
        query = query.filter(~time_sensitive_stale(ApplicationRecord))
    if first_quest_ok is not None:
        # "No experience needed", provably. Only rows whose source stated a
        # beginner-friendly signal carry the flag; career rows and unmarked
        # quest rows never have it, so they drop rather than get guessed in.
        if first_quest_ok:
            query = query.filter(ApplicationRecord.first_quest_ok.is_(True))
        else:
            query = query.filter(
                or_(
                    ApplicationRecord.first_quest_ok.is_(False),
                    ApplicationRecord.first_quest_ok.is_(None),
                )
            )
    if posted_within_days is not None:
        # "Posted in the last N days", provably. date_posted is a raw source
        # string, ISO-8601 when the source stated a real date and free text
        # ("Reposted 9 Days Ago") when it did not. Only rows whose stored
        # value sorts inside [now - N days, now + 1 day] count; ISO strings
        # compare correctly as text, and the future-bounded upper edge drops
        # every non-ISO value (letters and bare day counts sort above it).
        # A date-only string from yesterday cannot prove it is inside a
        # 24-hour window, so it does not count: undercounting is the honest
        # side of that ambiguity. Rows the classifier marked "missing" never
        # count even if a string survives.
        now = datetime.now(timezone.utc)
        lower = (now - timedelta(days=posted_within_days)).strftime("%Y-%m-%dT%H:%M:%S")
        upper = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        query = query.filter(
            ApplicationRecord.date_posted >= lower,
            ApplicationRecord.date_posted <= upper,
            func.lower(func.coalesce(ApplicationRecord.date_confidence, "")) != "missing",
        )
    if event_within_days is not None:
        # Rows whose taping/session date falls inside the next N days. Only
        # real event_start values count; rows with no event date are not
        # "happening this week". Stored values are naive UTC.
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        query = query.filter(
            ApplicationRecord.event_start.isnot(None),
            ApplicationRecord.event_start >= now_naive,
            ApplicationRecord.event_start <= now_naive + timedelta(days=event_within_days),
        )
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                ApplicationRecord.job_title.ilike(pattern),
                ApplicationRecord.company.ilike(pattern),
                ApplicationRecord.description.ilike(pattern),
                # a typed city must find the sit whose location says it
                ApplicationRecord.location.ilike(pattern),
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
        # yours, or a read of a shared quest row (the hosted board is one
        # felt for everyone; mutations clone first, reads need not)
        from sqlalchemy import and_, or_

        query = query.filter(
            or_(
                ApplicationRecord.workspace_id == workspace_id,
                and_(
                    ApplicationRecord.workspace_id.is_(None),
                    ApplicationRecord.vertical != "career",
                ),
            )
        )
    return query.first()


def create_application(db: Session, data, workspace_id: str | None = None) -> ApplicationRecord:
    """Create a new application record from an ApplicationCreate schema."""
    vertical = data.vertical or "career"
    if vertical not in APPLICATION_VERTICALS:
        raise ValueError(f"unknown application vertical: {vertical!r}")
    record = ApplicationRecord(
        job_title=data.job_title,
        company=data.company,
        location=data.location,
        # Empty URLs store as NULL so the unique constraint permits many
        # URL-less rows (personal quests have no source link), matching
        # job_finder save_application's convention.
        job_url=data.job_url or None,
        source=data.source,
        description=data.description,
        is_remote=data.is_remote,
        salary_min=data.salary_min,
        salary_max=data.salary_max,
        status=data.status,
        notes=data.notes,
        profile=data.profile,
        vertical=vertical,
        workspace_id=workspace_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _clone_shared_quest_row(
    db: Session, shared: ApplicationRecord, workspace_id: str
) -> ApplicationRecord:
    """Copy a shared quest row into a workspace (hosted clone-on-touch).

    The shared row stays pristine for everyone else; the copy is the
    user's, and board reads hide the original behind it (job_url dedupe).
    """
    values = {
        column.name: getattr(shared, column.name)
        for column in ApplicationRecord.__table__.columns
        if column.name != "id"
    }
    values["workspace_id"] = workspace_id
    copy = ApplicationRecord(**values)
    db.add(copy)
    db.flush()
    return copy


def update_application(
    db: Session,
    app_id: int,
    workspace_id: str | None = None,
    allow_quest_clone: bool = False,
    **kwargs,
) -> ApplicationRecord | None:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    record = query.first()
    if not record and workspace_id and allow_quest_clone:
        # hosted: the id may name a SHARED quest row; touch = clone first.
        # A stale client can send the shared id after a copy already
        # exists, so resolve to the existing copy by URL before cloning.
        from app.services.row_scope import shared_quest_row_filter

        shared = db.query(ApplicationRecord).filter(shared_quest_row_filter(app_id)).first()
        if shared is not None:
            record = (
                db.query(ApplicationRecord)
                .filter(
                    ApplicationRecord.workspace_id == workspace_id,
                    ApplicationRecord.job_url == shared.job_url,
                )
                .first()
            ) or _clone_shared_quest_row(db, shared, workspace_id)
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
    live_only: bool = False,
) -> dict:
    """HEAD-check job URLs and update url_status. Returns summary counts.

    ``live_only`` skips rows already off the board (dead/expired), so the
    scheduler's rolling re-verification never wastes its batch re-proving
    what is already tombstoned.
    """
    import requests as req

    query = db.query(ApplicationRecord).filter(ApplicationRecord.job_url.isnot(None))
    if live_only:
        query = query.filter(ApplicationRecord.url_status.notin_(("dead", "expired")))
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
