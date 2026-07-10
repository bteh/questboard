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


@dataclass
class SourceSchedule:
    name: str
    display_name: str
    vertical: str
    refresh_hours: int
    last_attempt_at: datetime | None   # newest run of any outcome
    due_at: datetime | None            # None = never ran, due immediately

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


def board_schedule(now: datetime | None = None) -> list[SourceSchedule]:
    """Every schedulable source with its due state, soonest-due first."""
    from job_finder.models.database import latest_scrape_attempts

    attempts = latest_scrape_attempts()
    out: list[SourceSchedule] = []
    for meta in schedulable_metas():
        last = attempts.get(meta.name)
        due_at = last + timedelta(hours=meta.refresh_hours) if last else None
        out.append(
            SourceSchedule(
                name=meta.name,
                display_name=meta.display_name,
                vertical=meta.vertical,
                refresh_hours=meta.refresh_hours,
                last_attempt_at=last,
                due_at=due_at,
            )
        )
    out.sort(key=lambda s: (s.due_at or datetime.min, s.name))
    return out


def due_sources(now: datetime | None = None) -> list[SourceSchedule]:
    """The sources a tick should sweep right now."""
    moment = now or _utcnow()
    return [s for s in board_schedule(moment) if s.due(moment)]
