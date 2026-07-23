"""Why is this opportunity hidden? A per-stage exclusion tracer.

A board row is hidden when exactly one filter stage drops it. This module
runs the SAME production predicates the read path uses, one stage at a time,
against a single target row, and reports which stage (if any) removed it. The
first stage that reports ``passed=False`` is the culprit.

Two kinds of predicate share one trace:

* SQL conditions (is_remote, location, salary, first_quest_ok, posted-date
  freshness, dead-link) are the exact SQLAlchemy conditions from
  ``application_service.board_filter_conditions`` /
  ``application_service.place_filter`` / ``stated_pay_filter``. We evaluate
  each against the single target row inside a throwaway in-memory SQLite set,
  so the trace uses the real predicate and can never drift, and never touches
  the caller's live database.
* Post-SQL Python filters (title/role match, anchored freshness, cross-source
  dedup) call the real functions in ``local_agent_service``.

The tracer covers BOTH lanes because they share the filter vocabulary: the
career/work lane (``local_agent_service.search_work``) and the side-quest lane
(``local_agent_service.search_side_quests``). Pass ``lane="work"`` or
``lane="quests"``; each stage marks itself applied or not-applied for that lane
and its filter set, so a not-applied stage always passes and never masks the
real blocker.

Nothing here writes to any database. SQL stages run against a fresh in-memory
copy of just the one row; the optional live session is opened read-only by the
caller and used only to resolve the target and read the dedup candidate pool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, literal, select
from sqlalchemy.orm import Session

from app.models.application import ApplicationRecord
from app.services import application_service, local_agent_service

# The canonical, ordered stages a board row passes through. The first five are
# the shared SQL read-path vocabulary (application_service.board_filter_conditions);
# the last four are applied after the SQL query by local_agent_service.search_work.
# Order matters: first applied stage that fails is the culprit.
STAGE_ORDER: tuple[str, ...] = (
    "is_remote",
    "location",
    "salary",
    "first_quest_ok",
    "freshness_sql",
    "dead_link",
    "title_match",
    "anchored_freshness",
    "dedup",
)

# Which stages each lane actually applies. A stage outside its lane's set is
# never a blocker (recorded applied=False, passed=True).
#   work   -> career/work lane, local_agent_service.search_work
#   quests -> side-quest lane, local_agent_service.search_side_quests
#   board  -> classic /applications read path (all SQL board conditions)
_LANE_STAGES: dict[str, frozenset[str]] = {
    "work": frozenset(
        {"is_remote", "location", "salary", "dead_link", "title_match",
         "anchored_freshness", "dedup"}
    ),
    "quests": frozenset({"location", "first_quest_ok", "dead_link"}),
    "board": frozenset(
        {"is_remote", "location", "salary", "first_quest_ok", "freshness_sql",
         "dead_link"}
    ),
}

# Column names any SQL stage references. We materialize only these (all
# String/Float/Boolean) into the in-memory row, so there is no DateTime
# coercion and no dependency on the target's other columns.
_SQL_COLUMNS: tuple[str, ...] = (
    "id",
    "job_title",
    "company",
    "location",
    "state_codes",
    "remote_scope",
    "is_remote",
    "salary_min",
    "salary_max",
    "salary_min_annualized",
    "salary_max_annualized",
    "salary_period",
    "first_quest_ok",
    "date_posted",
    "date_confidence",
    "url_status",
    "vertical",
)

# Friendly aliases accepted on a hypothetical (dict) row, mapped to ORM columns.
_ROW_ALIASES: dict[str, str] = {
    "title": "job_title",
    "organization": "company",
    "url": "job_url",
    "posted": "date_posted",
    "found": "date_found",
    "salary_period_raw": "salary_period",
}


@dataclass
class StageResult:
    """One filter stage's verdict for the traced row."""

    stage: str
    passed: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)
    applied: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "passed": self.passed,
            "applied": self.applied,
            "reason": self.reason,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Row resolution / materialization
# ---------------------------------------------------------------------------


def _row_to_data(rec: ApplicationRecord) -> dict[str, Any]:
    """Flatten an ApplicationRecord into a plain field dict."""
    return {c.name: getattr(rec, c.name, None) for c in ApplicationRecord.__table__.columns}


def _normalize_row_input(row: dict[str, Any]) -> dict[str, Any]:
    """Accept a hypothetical row dict with either ORM column names or friendly
    aliases, and fill an id so the in-memory SELECT can target it."""
    data: dict[str, Any] = {}
    for key, value in row.items():
        data[_ROW_ALIASES.get(key, key)] = value
    data.setdefault("id", 1)
    data.setdefault("job_title", data.get("job_title") or "")
    data.setdefault("company", data.get("company") or "")
    return data


def resolve_target(
    db: Session | None,
    *,
    row: dict[str, Any] | None = None,
    row_id: int | None = None,
    company: str | None = None,
    title: str | None = None,
    url: str | None = None,
    verticals: list[str] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Resolve the row to trace and return (row_data, human description).

    Priority: an explicit dict row, then an id, then a company+title/url best
    match against the live session. Returns (None, reason) when nothing matches.
    """
    if row is not None:
        return _normalize_row_input(row), "supplied row (hypothetical)"
    if db is None:
        return None, "no database session and no row supplied"

    query = application_service.scoped_applications(
        db.query(ApplicationRecord), verticals
    )
    if row_id is not None:
        rec = query.filter(ApplicationRecord.id == int(row_id)).first()
        if rec is None:
            # An id is explicit; do not silently fall back to a fuzzy match.
            rec = db.query(ApplicationRecord).filter(
                ApplicationRecord.id == int(row_id)
            ).first()
        if rec is None:
            return None, f"no row with id={row_id}"
        return _row_to_data(rec), f"id={rec.id} ({rec.company} / {rec.job_title})"

    conditions = []
    if company:
        conditions.append(ApplicationRecord.company.ilike(f"%{company.strip()}%"))
    if title:
        conditions.append(ApplicationRecord.job_title.ilike(f"%{title.strip()}%"))
    if url:
        conditions.append(ApplicationRecord.job_url == url.strip())
    if not conditions:
        return None, "no id, company, title, url, or row supplied"

    match = (
        query.filter(*conditions)
        .order_by(ApplicationRecord.date_found.desc())
        .first()
    )
    if match is None:
        wanted = " + ".join(
            p for p in (company and f"company~{company!r}", title and f"title~{title!r}",
                        url and f"url={url!r}") if p
        )
        return None, f"no board row matches {wanted}"
    return _row_to_data(match), f"id={match.id} ({match.company} / {match.job_title})"


class _OneRowSet:
    """A throwaway in-memory SQLite set holding exactly the target row, for
    evaluating real SQL conditions without touching the live database."""

    def __init__(self, row_data: dict[str, Any]):
        self._engine = create_engine("sqlite:///:memory:")
        ApplicationRecord.__table__.create(self._engine)
        table = ApplicationRecord.__table__
        cols: dict[str, Any] = {}
        for name in _SQL_COLUMNS:
            if name not in table.columns:
                continue
            value = row_data.get(name)
            if value is None:
                # Fall back to the column's own scalar default so a bare
                # hypothetical row behaves like a freshly-saved one
                # (url_status "unknown", is_remote False, location "", ...).
                default = table.columns[name].default
                if default is not None and getattr(default, "is_scalar", False):
                    value = default.arg
            cols[name] = value
        cols["id"] = int(row_data.get("id") or 1)
        cols["job_title"] = cols.get("job_title") or ""
        cols["company"] = cols.get("company") or ""
        # vertical is NOT NULL; a hypothetical row may omit it.
        cols["vertical"] = cols.get("vertical") or "career"
        self._id = cols["id"]
        with self._engine.begin() as conn:
            conn.execute(ApplicationRecord.__table__.insert().values(**cols))

    def passes(self, condition) -> bool:
        """True when the single row satisfies the SQLAlchemy boolean condition."""
        stmt = select(literal(1)).where(
            ApplicationRecord.id == self._id
        ).where(condition)
        with self._engine.connect() as conn:
            return conn.execute(stmt).first() is not None

    def dispose(self) -> None:
        self._engine.dispose()


# ---------------------------------------------------------------------------
# The trace
# ---------------------------------------------------------------------------


def _single_board_condition(**kwargs):
    """Exactly one stage's SQL condition, built by the production board vocabulary.

    board_filter_conditions returns a list (freshness returns three); AND them so
    the stage is one predicate. Returns None when the filter is unset.
    """
    from sqlalchemy import and_

    conds = application_service.board_filter_conditions(ApplicationRecord, **kwargs)
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return and_(*conds)


def _dedup_survives(
    db: Session,
    target: dict[str, Any],
    filters: dict[str, Any],
    verticals: list[str],
) -> tuple[bool, dict[str, Any]]:
    """Replay search_work's cross-source dedup for the target row.

    Rebuilds the same candidate set search_work retrieves (title token groups,
    location, salary floor, is_remote, exclude_dead), applies the same title +
    anchored-freshness survivors filter, then runs the identical keep-the-best
    dict using the real _dedupe_work_key / _dedupe_work_priority. The target
    survives iff it is the keeper for its key.
    """
    roles = list(filters.get("roles") or [])
    role_groups = [
        [tok for tok in sorted(local_agent_service._role_tokens(term))
         if tok not in local_agent_service._LEVEL_TOKENS]
        for term in roles
    ]
    role_groups = [g for g in role_groups if g]
    rows, _ = application_service.get_applications(
        db,
        title_token_groups=role_groups or None,
        is_remote=filters.get("is_remote"),
        location=filters.get("location") or None,
        location_strict=bool(filters.get("location_strict")),
        salary_min=filters.get("salary_min"),
        exclude_dead=True,
        sort_by="date_found",
        sort_dir="desc",
        page=1,
        page_size=1000,
        verticals=verticals,
    )
    target_id = target.get("id")
    if target_id is not None and not any(r.id == target_id for r in rows):
        # The target itself was dropped by an earlier SQL stage; dedup is not
        # the blocker. Report survives=True so an earlier stage owns the verdict.
        return True, {"note": "target not in candidate set (earlier stage dropped it)"}

    survivors: list[ApplicationRecord] = []
    window = filters.get("posted_within_days")
    explicit = bool(filters.get("freshness_explicit"))
    for r in rows:
        if roles and not local_agent_service._title_is_in_lane(r.job_title, roles):
            continue
        age = local_agent_service._source_age_days(r.date_posted, r.date_found)
        if window is not None and age is not None:
            if age > window:
                continue
        elif explicit:
            continue
        survivors.append(r)

    unique: dict[Any, ApplicationRecord] = {}
    for r in survivors:
        key = local_agent_service._dedupe_work_key(r)
        existing = unique.get(key)
        if existing is None:
            unique[key] = r
            continue
        if local_agent_service._dedupe_work_priority(r) > local_agent_service._dedupe_work_priority(existing):
            unique[key] = r

    keeper = None
    if target_id is not None:
        target_row = next((r for r in survivors if r.id == target_id), None)
        if target_row is not None:
            keeper = unique.get(local_agent_service._dedupe_work_key(target_row))
    survives = keeper is None or (target_id is not None and keeper.id == target_id)
    detail: dict[str, Any] = {"candidate_count": len(rows), "survivor_count": len(survivors)}
    if not survives and keeper is not None:
        detail["kept_instead"] = {
            "id": keeper.id,
            "company": keeper.company,
            "title": keeper.job_title,
            "source": keeper.source,
        }
    return survives, detail


def trace_exclusion(
    db: Session | None = None,
    *,
    row: dict[str, Any] | None = None,
    row_id: int | None = None,
    company: str | None = None,
    title: str | None = None,
    url: str | None = None,
    filters: dict[str, Any] | None = None,
    lane: str = "work",
) -> list[StageResult]:
    """Trace a single row through every filter stage, in order.

    Returns the ordered list of StageResult; the first with ``passed=False``
    (and ``applied=True``) is the culprit. See ``first_blocker`` / ``verdict``.

    ``filters`` carries the user's real filter values (location, location_strict,
    salary_min/max, is_remote, first_quest_ok, posted_within_days,
    freshness_explicit, roles). Build it from saved preferences with
    ``saved_filters`` or supply your own.
    """
    filters = dict(filters or {})
    lane = lane if lane in _LANE_STAGES else "work"
    applies = _LANE_STAGES[lane]
    verticals = filters.get("verticals") or (
        ["career", "work"] if lane == "work" else None
    )

    row_data, source_desc = resolve_target(
        db, row=row, row_id=row_id, company=company, title=title, url=url,
        verticals=verticals,
    )
    if row_data is None:
        return [StageResult("resolve", False, source_desc, {"resolved": False}, applied=True)]

    one_row = _OneRowSet(row_data)
    results: list[StageResult] = []
    try:
        for stage in STAGE_ORDER:
            applied = stage in applies
            results.append(
                _run_stage(stage, applied, one_row, db, row_data, filters, verticals, source_desc)
            )
    finally:
        one_row.dispose()
    return results


def _run_stage(stage, applied, one_row, db, row_data, filters, verticals, source_desc) -> StageResult:
    if not applied:
        return StageResult(stage, True, "not applied in this lane", {"applied": False}, applied=False)

    if stage == "is_remote":
        want = filters.get("is_remote")
        if want is None:
            return StageResult(stage, True, "no is_remote filter set", applied=False)
        cond = _single_board_condition(is_remote=want)
        ok = one_row.passes(cond)
        return StageResult(
            stage, ok,
            "matches is_remote filter" if ok else f"row is_remote={row_data.get('is_remote')} != {want}",
            {"filter_is_remote": want, "row_is_remote": row_data.get("is_remote")},
        )

    if stage == "location":
        loc = filters.get("location")
        if not loc:
            return StageResult(stage, True, "no location filter set", applied=False)
        strict = bool(filters.get("location_strict"))
        cond = application_service.place_filter(ApplicationRecord, loc, location_strict=strict)
        if cond is None:
            return StageResult(stage, True, "no location filter set", applied=False)
        ok = one_row.passes(cond)
        return StageResult(
            stage, ok,
            "reachable from your place" if ok
            else f"location {row_data.get('location')!r} not reachable from {loc!r}"
                 + (" (near-me only)" if strict else ""),
            {"filter_location": loc, "location_strict": strict,
             "row_location": row_data.get("location"),
             "row_remote_scope": row_data.get("remote_scope")},
        )

    if stage == "salary":
        smin = filters.get("salary_min")
        smax = filters.get("salary_max")
        if smin is None and smax is None:
            return StageResult(stage, True, "no salary filter set", applied=False)
        cond = application_service.stated_pay_filter(ApplicationRecord, smin, smax)
        if cond is None:
            return StageResult(stage, True, "no salary filter set", applied=False)
        ok = one_row.passes(cond)
        return StageResult(
            stage, ok,
            "clears the pay filter (or no/session pay stated, kept)" if ok
            else f"stated pay out of [{smin}, {smax}] (period={row_data.get('salary_period')!r})",
            {"salary_min": smin, "salary_max": smax,
             "row_salary_min": row_data.get("salary_min"),
             "row_salary_max": row_data.get("salary_max"),
             "row_salary_period": row_data.get("salary_period")},
        )

    if stage == "first_quest_ok":
        want = filters.get("first_quest_ok")
        if want is None:
            return StageResult(stage, True, "no no-experience filter set", applied=False)
        cond = _single_board_condition(first_quest_ok=want)
        ok = one_row.passes(cond)
        return StageResult(
            stage, ok,
            "matches the no-experience filter" if ok
            else ("row is not flagged beginner-friendly" if want
                  else "row is flagged first_quest_ok"),
            {"filter_first_quest_ok": want, "row_first_quest_ok": row_data.get("first_quest_ok")},
        )

    if stage == "freshness_sql":
        window = filters.get("posted_within_days")
        if window is None:
            return StageResult(stage, True, "no posted-within-days filter set", applied=False)
        cond = _single_board_condition(posted_within_days=int(window))
        ok = one_row.passes(cond)
        return StageResult(
            stage, ok,
            f"posted date sorts inside the {window}-day window" if ok
            else f"date_posted {row_data.get('date_posted')!r} "
                 f"(confidence={row_data.get('date_confidence')!r}) outside {window}-day window",
            {"posted_within_days": window, "row_date_posted": row_data.get("date_posted"),
             "row_date_confidence": row_data.get("date_confidence")},
        )

    if stage == "dead_link":
        # The exact production predicate from get_applications(exclude_dead=True):
        # ApplicationRecord.url_status.notin_(("dead", "expired")).
        cond = ApplicationRecord.url_status.notin_(("dead", "expired"))
        ok = one_row.passes(cond)
        return StageResult(
            stage, ok,
            "link is not dead/expired" if ok
            else f"url_status={row_data.get('url_status')!r} is dead/expired",
            {"row_url_status": row_data.get("url_status")},
        )

    if stage == "title_match":
        roles = list(filters.get("roles") or [])
        if not roles:
            return StageResult(stage, True, "no target roles set", applied=False)
        ok = local_agent_service._title_is_in_lane(row_data.get("job_title"), roles)
        return StageResult(
            stage, ok,
            "title is in one of your role lanes" if ok
            else f"title {row_data.get('job_title')!r} is not in any target role lane",
            {"roles": roles, "row_title": row_data.get("job_title")},
        )

    if stage == "anchored_freshness":
        window = filters.get("posted_within_days")
        explicit = bool(filters.get("freshness_explicit"))
        age = local_agent_service._source_age_days(
            row_data.get("date_posted"), row_data.get("date_found")
        )
        if window is None:
            return StageResult(stage, True, "no freshness window set", applied=False,
                               detail={"anchored_age_days": age})
        if age is not None:
            ok = age <= window
            return StageResult(
                stage, ok,
                f"anchored age {age:.1f}d within {window}d" if ok
                else f"anchored age {age:.1f}d older than {window}d window",
                {"anchored_age_days": age, "window": window},
            )
        # Unknown age: search_work keeps it under saved defaults (agent review),
        # drops it only under an explicit freshness request.
        if explicit:
            return StageResult(
                stage, False,
                f"date unreadable and an explicit {window}-day window drops unknowns",
                {"anchored_age_days": None, "window": window, "explicit": True},
            )
        return StageResult(
            stage, True,
            "date unreadable; kept for agent review (saved-default window)",
            {"anchored_age_days": None, "window": window, "explicit": False},
        )

    if stage == "dedup":
        if db is None:
            return StageResult(stage, True, "no session; dedup pool empty", applied=False)
        survives, detail = _dedup_survives(db, row_data, filters, verticals or ["career", "work"])
        return StageResult(
            stage, survives,
            "kept as the best copy of this posting" if survives
            else "a higher-priority duplicate from another source outranks it",
            detail,
        )

    return StageResult(stage, True, "unknown stage", applied=False)


def first_blocker(results: list[StageResult]) -> StageResult | None:
    """The first applied stage that failed, or None when the row is visible."""
    for r in results:
        if r.applied and not r.passed:
            return r
    return None


def verdict(results: list[StageResult]) -> str:
    """One-line human verdict naming the blocking stage, or 'visible'."""
    blocker = first_blocker(results)
    if blocker is None:
        return "visible on the board"
    return f"hidden by {blocker.stage}: {blocker.reason}"


# ---------------------------------------------------------------------------
# Saved-preference filter defaults (the user's real settings)
# ---------------------------------------------------------------------------


def saved_filters(
    db: Session, *, workspace_id: str | None = None, lane: str = "work"
) -> dict[str, Any]:
    """Build the filters dict from the user's saved workspace preferences.

    Uses the real local_agent_service._saved_search_defaults (roles, place,
    workplace, max_days_old, floor). Falls back to a minimal raw read if the
    ORM preferences load fails (e.g. a schema migration in flight), so the CLI
    still reflects the person's real place/floor/roles.
    """
    try:
        roles, place, workplace, days, floor = local_agent_service._saved_search_defaults(
            db, workspace_id
        )
    except Exception:
        roles, place, workplace, days, floor = _saved_defaults_fallback(db, workspace_id)

    window = max(1, min(int(days or 30), 365))
    filters: dict[str, Any] = {
        "location": place or None,
        "location_strict": bool(place) and workplace == "location_only",
        "salary_min": floor,
        "salary_max": None,
        "is_remote": True if workplace == "remote_only" else None,
        "first_quest_ok": None,
        "posted_within_days": window,
        "freshness_explicit": False,
        "roles": list(roles or []),
        "workplace_preference": workplace,
    }
    if lane == "quests":
        # Side quests do not filter on salary, is_remote, roles, or freshness;
        # they filter on place, first_quest_ok, dead-link (and event window).
        filters.update(
            salary_min=None, is_remote=None, roles=[], posted_within_days=None
        )
    return filters


def _saved_defaults_fallback(
    db: Session, workspace_id: str | None
) -> tuple[list[str], str, str, int, float | None]:
    """Read only the columns that exist, so schema drift can't crash defaults."""
    import json

    from sqlalchemy import text

    ws = local_agent_service.resolve_local_workspace(db, workspace_id)
    if ws is None:
        return [], "", "remote_friendly", 30, None
    row = db.execute(
        text(
            "SELECT roles_json, preferred_places_json, workplace_preference, "
            "max_days_old, min_base, min_acceptable_tc, current_title "
            "FROM workspace_preferences WHERE workspace_id = :w"
        ),
        {"w": ws.id},
    ).mappings().first()
    if row is None:
        return [], "", "remote_friendly", 30, None

    def _loads(value):
        try:
            return json.loads(value) if value else []
        except (TypeError, ValueError):
            return []

    places = _loads(row["preferred_places_json"])
    place = ""
    for item in places:
        label = (item.get("label") or "").strip()
        if label and label.lower() not in {"remote", "anywhere"}:
            place = label
            break
    roles = [str(r) for r in _loads(row["roles_json"]) if str(r).strip()]
    if not roles and (row["current_title"] or "").strip():
        roles = [row["current_title"].strip()]
    floor = row["min_base"] or row["min_acceptable_tc"]
    days = int(row["max_days_old"] or 30)
    workplace = row["workplace_preference"] or "remote_friendly"
    return roles, place, workplace, days, floor
