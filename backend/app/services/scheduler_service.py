"""The board scheduler: quest sources sweep themselves on their cadence.

An asyncio loop owned by the app lifespan. Every tick it asks
job_finder.schedule which sources are due (cadence declared per source in
the registry, measured from the last attempt in the run log) and runs
exactly those through run_quest_search, which already carries the whole
trust machinery: snapshot before writes, run logging, dedup, expiry.

Design constraints:
- One sweep at a time. A tick that lands while a sweep is running is
  skipped, not queued; the next tick recomputes due-ness from the log.
- Local pool only (workspace_id=None). Hosted mode never starts the loop;
  hosted sweeps need the shared-pool design that lands with hosting.
- The first check waits scheduler_initial_delay_seconds so short-lived
  app contexts (tests, smoke runs) never fire a sweep.
- Scrapers are sync code; the sweep runs in a worker thread so the event
  loop keeps serving requests.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


class BoardScheduler:
    def __init__(
        self,
        tick_seconds: int,
        initial_delay_seconds: int,
    ) -> None:
        self._tick_seconds = max(60, tick_seconds)
        self._initial_delay = max(0, initial_delay_seconds)
        self._task: asyncio.Task | None = None
        self._sweeping = asyncio.Lock()
        self.sweeps_run = 0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(
                self._loop(), name="board-scheduler"
            )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(self._initial_delay)
        while True:
            try:
                await self.tick()
            except Exception:
                # A broken tick must never kill the loop; the run log and
                # /health carry the evidence of what went wrong.
                logger.exception("board scheduler: tick failed")
            await asyncio.sleep(self._tick_seconds)

    async def tick(self) -> int:
        """Sweep every due source. Returns how many sources were swept."""
        if self._sweeping.locked():
            logger.info("board scheduler: sweep still running, tick skipped")
            return 0
        async with self._sweeping:
            from job_finder.schedule import due_sources

            due = await asyncio.to_thread(due_sources)
            if not due:
                return 0
            names = [s.name for s in due]
            verticals = sorted({s.vertical for s in due})
            logger.info("board scheduler: sweeping %s", ", ".join(names))

            from job_finder.quests import run_quest_search

            summary = await asyncio.to_thread(
                lambda: run_quest_search(
                    verticals=verticals,
                    only_sources=names,
                    workspace_id=None,
                )
            )
            self.sweeps_run += 1
            logger.info(
                "board scheduler: swept %d sources, %d found, %d saved, %d expired",
                len(names),
                summary.get("found", 0),
                summary.get("saved", 0),
                summary.get("expired", 0),
            )
            return len(names)


def build_scheduler() -> BoardScheduler | None:
    """The lifespan's factory: a scheduler when configuration allows one."""
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("board scheduler: disabled by configuration")
        return None
    if settings.hosted_mode:
        logger.info("board scheduler: hosted mode, not starting (see hosting build)")
        return None
    return BoardScheduler(
        tick_seconds=settings.scheduler_tick_seconds,
        initial_delay_seconds=settings.scheduler_initial_delay_seconds,
    )
