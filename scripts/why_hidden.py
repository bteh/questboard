#!/usr/bin/env python
"""why_hidden.py — trace why a Questboard opportunity is hidden from the board.

Runs the real filter stages against one row and prints a per-stage PASS/DROP
table plus a one-line verdict naming the blocking stage (or "visible on the
board"). Defaults to your saved workspace filters (location, salary floor,
workplace, roles, posted window).

    python scripts/why_hidden.py --company "BILL" --title "Staff Data Engineer"
    python scripts/why_hidden.py --id 2943
    python scripts/why_hidden.py --url "https://.../jobs/123" --lane quests

Safety: never mutates your board. It copies the live SQLite database (plus its
-wal/-shm) to a temp file and reads only the copy. Use --db to point at another
database.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

DEFAULT_DB = ROOT / "backend" / "data" / "job_tracker.db"


def _read_only_copy(db_path: Path, workdir: Path):
    """Copy the SQLite db (+wal/+shm) into workdir and return a Session on the
    copy. The live database is never opened for writing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    copy = workdir / "board_copy.db"
    shutil.copy2(db_path, copy)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            shutil.copy2(side, workdir / ("board_copy.db" + suffix))
    engine = create_engine(f"sqlite:///{copy}")
    return Session(engine)


def _hypothetical_from_args(args) -> dict:
    """Build a hypothetical row dict from the CLI fields (used when no live row
    matches, so you can still ask "would a posting like this be hidden?")."""
    row: dict = {}
    if args.title:
        row["job_title"] = args.title
    if args.company:
        row["company"] = args.company
    if args.url:
        row["job_url"] = args.url
    if args.row_location is not None:
        row["location"] = args.row_location
    if args.remote_scope is not None:
        row["remote_scope"] = args.remote_scope
    if args.is_remote is not None:
        row["is_remote"] = args.is_remote
    if args.date_posted is not None:
        row["date_posted"] = args.date_posted
    if args.url_status is not None:
        row["url_status"] = args.url_status
    if args.salary_period is not None:
        row["salary_period"] = args.salary_period
    if args.row_salary_min is not None:
        row["salary_min"] = args.row_salary_min
    if args.row_salary_max is not None:
        row["salary_max"] = args.row_salary_max
    if args.vertical is not None:
        row["vertical"] = args.vertical
    return row


def _apply_filter_overrides(filters: dict, args) -> dict:
    if args.location is not None:
        filters["location"] = args.location or None
    if args.near_me_only:
        filters["location_strict"] = True
    if args.salary_min is not None:
        filters["salary_min"] = args.salary_min
    if args.salary_max is not None:
        filters["salary_max"] = args.salary_max
    if args.posted_within_days is not None:
        filters["posted_within_days"] = args.posted_within_days
        # An explicit window is a hard constraint: unknown dates drop.
        filters["freshness_explicit"] = True
    if args.first_quest_ok is not None:
        filters["first_quest_ok"] = args.first_quest_ok
    return filters


def _print_table(results) -> None:
    stage_w = max(len(r.stage) for r in results)
    print()
    print(f"  {'STAGE'.ljust(stage_w)}  RESULT  REASON")
    print(f"  {'-' * stage_w}  ------  {'-' * 48}")
    for r in results:
        if not r.applied:
            mark = "  --  "
        elif r.passed:
            mark = " PASS "
        else:
            mark = " DROP "
        print(f"  {r.stage.ljust(stage_w)}  {mark}  {r.reason}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Trace why a Questboard opportunity is hidden.",
    )
    target = parser.add_argument_group("target (choose how to find the row)")
    target.add_argument("--company", help="company / organization name")
    target.add_argument("--title", help="job or quest title")
    target.add_argument("--url", help="exact job_url to match")
    target.add_argument("--id", dest="row_id", type=int, help="ApplicationRecord id")

    parser.add_argument("--lane", choices=["work", "quests"], default="work",
                        help="career/work lane (default) or side-quest lane")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="path to the SQLite board (default: backend/data/job_tracker.db)")

    flt = parser.add_argument_group("filter overrides (default: your saved settings)")
    flt.add_argument("--location", help="seeker location (empty string clears it)")
    flt.add_argument("--near-me-only", action="store_true", help="strict location match")
    flt.add_argument("--salary-min", type=float, help="pay floor (annual scale)")
    flt.add_argument("--salary-max", type=float, help="pay ceiling (annual scale)")
    flt.add_argument("--posted-within-days", type=int, help="freshness window in days")
    flt.add_argument("--first-quest-ok", type=lambda v: v.lower() in ("1", "true", "yes"),
                    help="require beginner-friendly (quests lane)")

    hyp = parser.add_argument_group("hypothetical row fields (used if no live row matches)")
    hyp.add_argument("--row-location", help="the posting's location text")
    hyp.add_argument("--remote-scope", help="remote_scope (e.g. intl)")
    hyp.add_argument("--is-remote", type=lambda v: v.lower() in ("1", "true", "yes"))
    hyp.add_argument("--date-posted", help="raw source date string")
    hyp.add_argument("--url-status", help="url_status (alive/dead/expired/unknown)")
    hyp.add_argument("--salary-period", help="hourly/daily/weekly/monthly/yearly/session")
    hyp.add_argument("--row-salary-min", type=float)
    hyp.add_argument("--row-salary-max", type=float)
    hyp.add_argument("--vertical", help="row vertical (career/work/lookafter/...)")

    args = parser.parse_args(argv)
    if not (args.company or args.title or args.url or args.row_id):
        parser.error("give at least one of --company, --title, --url, --id")

    if not args.db.exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 2

    from app.services import exclusion_trace as et

    with tempfile.TemporaryDirectory(prefix="why_hidden_") as tmp:
        db = _read_only_copy(args.db, Path(tmp))
        try:
            filters = et.saved_filters(db, lane=args.lane)
            filters = _apply_filter_overrides(filters, args)

            verticals = ["career", "work"] if args.lane == "work" else (
                [args.vertical] if args.vertical else None
            )
            row_data, source_desc = et.resolve_target(
                db, row_id=args.row_id, company=args.company,
                title=args.title, url=args.url, verticals=verticals,
            )

            hypothetical = False
            if row_data is None and not args.row_id:
                hypothetical = True
                hyp_row = _hypothetical_from_args(args)
                results = et.trace_exclusion(
                    db, row=hyp_row, filters=filters, lane=args.lane
                )
                source_desc = "hypothetical row from your inputs (no live board row matched)"
            elif row_data is None:
                print(f"could not resolve target: {source_desc}", file=sys.stderr)
                return 1
            else:
                results = et.trace_exclusion(
                    db, row_id=row_data.get("id"),
                    company=args.company, title=args.title, url=args.url,
                    filters=filters, lane=args.lane,
                )

            print(f"target : {source_desc}")
            print(f"lane   : {args.lane}")
            loc = filters.get("location")
            print(
                "filters: "
                f"location={loc!r} strict={filters.get('location_strict')} "
                f"salary_min={filters.get('salary_min')} "
                f"is_remote={filters.get('is_remote')} "
                f"window={filters.get('posted_within_days')}d "
                f"roles={len(filters.get('roles') or [])}"
            )
            _print_table(results)
            v = et.verdict(results)
            prefix = "VERDICT (hypothetical): " if hypothetical else "VERDICT: "
            print(prefix + v)
            return 0
        finally:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
