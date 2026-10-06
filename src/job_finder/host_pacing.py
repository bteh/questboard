"""One in-flight request per host, spaced HOST_SPACING_SECONDS apart.

check_urls fans a batch across a 16-wide pool because posting URLs span many
hosts; within one host that fan-out is a burst. Measured Oct 6 2026 on a
200-row batch: 79 of 87 LinkedIn HEADs answered 429 inside 25 seconds,
Greenhouse 403'd after ~60 requests, BuiltIn 429'd after ~110, and every
walled row lost its alive stamp to "unknown". The pool stays wide across
hosts; requests to one host queue here, one at a time, a beat apart.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Callable, TypeVar
from urllib.parse import urlparse

HOST_SPACING_SECONDS = 1.0

T = TypeVar("T")


class HostPacer:
    """Serialize callables per host and sleep out the remaining spacing.

    ``sleeper`` and ``clock`` are injectable so tests never wait.
    """

    def __init__(
        self,
        spacing: float | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._spacing = HOST_SPACING_SECONDS if spacing is None else spacing
        self._sleep = sleeper
        self._clock = clock
        self._guard = Lock()
        self._locks: dict[str, Lock] = {}
        self._last_done: dict[str, float] = {}

    def run(self, url: str, request: Callable[[], T]) -> T:
        host = (urlparse(url).hostname or "").casefold()
        with self._guard:
            lock = self._locks.setdefault(host, Lock())
        with lock:
            last = self._last_done.get(host)
            if last is not None:
                wait = self._spacing - (self._clock() - last)
                if wait > 0:
                    self._sleep(wait)
            try:
                return request()
            finally:
                self._last_done[host] = self._clock()
