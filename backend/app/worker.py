"""Hosted background worker entrypoint for durable search jobs."""

from __future__ import annotations

import logging
import os
import socket
import time

from app.config import get_settings
from app.models.database import get_db, init_db
from app.services import pipeline_service, workspace_service

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    settings = get_settings()
    return settings.worker_id or f"{socket.gethostname()}-{os.getpid()}"


def _tick_heartbeat(status: str) -> None:
    settings = get_settings()
    db_gen = get_db()
    db = next(db_gen)
    try:
        workspace_service.update_worker_heartbeat(
            db,
            _worker_id(),
            worker_type="search",
            status=status,
            metadata={
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "release": settings.resolved_app_release,
            },
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def main() -> None:
    settings = get_settings()
    os.environ["DATABASE_URL"] = settings.resolved_database_url
    os.environ["JOB_FINDER_DATABASE_URL"] = settings.resolved_database_url
    os.environ["JOB_FINDER_DATA_DIR"] = settings.data_dir
    os.environ["JOB_FINDER_MANAGE_SCHEMA"] = "false"
    init_db()
    logger.info("Launchboard worker started", extra={"worker_id": _worker_id()})

    while True:
        try:
            _tick_heartbeat("running")
            processed = pipeline_service.process_next_hosted_run(_worker_id())
            _tick_heartbeat("busy" if processed else "idle")
            time.sleep(0 if processed else max(settings.worker_poll_interval_seconds, 0.5))
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("Launchboard worker loop failed", extra={"worker_id": _worker_id()})
            _tick_heartbeat("error")
            time.sleep(max(settings.worker_poll_interval_seconds, 0.5))


if __name__ == "__main__":
    main()
