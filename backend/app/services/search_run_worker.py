"""Persistent desktop owner for assistant-started career refreshes."""

from __future__ import annotations

import asyncio
import logging
import os
import socket

from app.config import get_settings

logger = logging.getLogger(__name__)


class DesktopSearchRunWorker:
    """Drain durable search rows from the long-lived desktop API process.

    The connected assistant talks through a short-lived stdio MCP subprocess.
    That subprocess may enqueue a refresh, but it must never own the network
    threads: the assistant exiting would kill them before source results save.
    """

    def __init__(self, poll_seconds: float = 0.5) -> None:
        self._poll_seconds = max(0.1, float(poll_seconds))
        self._task: asyncio.Task | None = None
        self._worker_id = f"desktop-api-{socket.gethostname()}-{os.getpid()}"

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(
                self._loop(), name="desktop-search-run-worker"
            )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        from app.services import pipeline_service

        while True:
            try:
                processed = await asyncio.to_thread(
                    pipeline_service.process_next_persisted_run,
                    self._worker_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("desktop search worker: durable run failed")
                processed = False
            if not processed:
                await asyncio.sleep(self._poll_seconds)


def build_desktop_search_worker() -> DesktopSearchRunWorker | None:
    settings = get_settings()
    if settings.hosted_mode:
        return None
    return DesktopSearchRunWorker(poll_seconds=settings.worker_poll_interval_seconds)
