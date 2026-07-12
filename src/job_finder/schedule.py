"""The board restocks itself: which sources are due for a sweep, and when.

Each quest source declares its own refresh cadence in its registry entry
(`refresh_hours`, like the expiry contract). This module answers one
question from the run log: which sources are due right now? Cadence is
measured from the last ATTEMPT, not the last success, so a broken source
retries at its normal rhythm instead of hammering a site that is already
telling us no; /health flags the breakage, the scheduler stays polite.

The loop that acts on this lives in the backend
(app.services.scheduler_service); keeping the decision here means it is
plain, offline-testable code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# The circuit breaker: after this many consecutive failed runs
# (exception/timeout) a source backs off beyond its normal cadence, so a
# site that starts blocking or 429-storming is retried ever less often
# instead of on its usual rhythm forever (which risks escalating a soft
# block to an IP ban and floods the run log with the same failure). The
# wait multiplies the cadence, doubling per failure past the threshold
# and capped, so a failing source always at least doubles its wait yet
# never gets abandoned. One healthy run closes the breaker.
BREAKER_THRESHOLD = 3
BREAKER_MAX_BACKOFF_HOURS = 72


@dataclass
class SourceSchedule:
    name: str
    display_name: str
    vertical: str
    refresh_hours: int
    last_attempt_at: datetime | None   # newest run of any outcome
    due_at: datetime | None            # None = never ran, due immediately
    failure_streak: int = 0            # consecutive exception/timeout runs
    breaker_open: bool = False         # backing off after repeated failure

    def due(self, now: datetime | None = None) -> bool:
        if self.due_at is None:
            return True
        return (now or _utcnow()) >= self.due_at


def schedulable_metas() -> list:
    """Quest sources the scheduler may ever run: a declared cadence, a
    search function, never career, never research_only."""
    from job_finder.tools.scrapers import get_registry

    return [
        meta
        for meta in get_registry().values()
        if meta.search_fn is not None
        and meta.vertical != "career"
        and not meta.research_only
        and meta.refresh_hours
    ]


def failure_streaks() -> dict[str, int]:
    """Consecutive most-recent failed runs (exception/timeout) per source.

    A streak breaks on the first non-failure, so one healthy run closes
    the breaker. Empty on any read failure (the breaker is best-effort:
    an unreadable log must never stop the board sweeping)."""
    from job_finder.models.database import get_recent_scrape_runs

    runs = get_recent_scrape_runs(days=14)  # newest first
    by_source: dict[str, int] = {}
    done: set[str] = set()
    for run in runs:
        if run.source in done:
            continue
        if run.finish_reason in ("exception", "timeout"):
            by_source[run.source] = by_source.get(run.source, 0) + 1
        else:
            done.add(run.source)  # streak ended at the newest healthy run
    return by_source


def _breaker_backoff_hours(refresh_hours: int, streak: int) -> float:
    """The wait for a source in a failure streak: its cadence times a
    factor that doubles per failure past the threshold (2x at the
    threshold, 4x, 8x...), capped. Always at least double the cadence."""
    factor = 2 ** (streak - BREAKER_THRESHOLD + 1)
    return min(refresh_hours * factor, BREAKER_MAX_BACKOFF_HOURS)


def board_schedule(now: datetime | None = None) -> list[SourceSchedule]:
    """Every schedulable source with its due state, soonest-due first."""
    from job_finder.models.database import latest_scrape_attempts

    attempts = latest_scrape_attempts()
    streaks = failure_streaks()
    out: list[SourceSchedule] = []
    for meta in schedulable_metas():
        last = attempts.get(meta.name)
        due_at = last + timedelta(hours=meta.refresh_hours) if last else None
        streak = streaks.get(meta.name, 0)
        breaker_open = False
        if last is not None and streak >= BREAKER_THRESHOLD:
            # the backoff always exceeds the cadence, so it replaces the
            # ordinary due time: a failing source waits longer, never less
            due_at = last + timedelta(
                hours=_breaker_backoff_hours(meta.refresh_hours, streak)
            )
            breaker_open = True
        out.append(
            SourceSchedule(
                name=meta.name,
                display_name=meta.display_name,
                vertical=meta.vertical,
                refresh_hours=meta.refresh_hours,
                last_attempt_at=last,
                due_at=due_at,
                failure_streak=streak,
                breaker_open=breaker_open,
            )
        )
    out.sort(key=lambda s: (s.due_at or datetime.min, s.name))
    return out


def due_sources(now: datetime | None = None) -> list[SourceSchedule]:
    """The sources a tick should sweep right now."""
    moment = now or _utcnow()
    return [s for s in board_schedule(moment) if s.due(moment)]
