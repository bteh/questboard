"""Fetch a page off someone's own site: robots.txt first, one request per host.

Used for sites the user names (watched careers pages), where no one has
hand-checked the site's robots.txt the way each fixed scraper's docstring
records. robots.txt is read once per host per process and obeyed for the
generic agent; requests to one host go through job_finder.host_pacing.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from job_finder import host_pacing

logger = logging.getLogger(__name__)

ROBOTS_AGENT = "Questboard"
_TIMEOUT = 15
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

_pacer_lock = Lock()
_pacer: host_pacing.HostPacer | None = None
_robots_lock = Lock()
_robots: dict[str, tuple[RobotFileParser, float]] = {}
_ROBOTS_TTL_S = 24 * 3600


class FetchError(Exception):
    """A page could not be read. The message is plain enough to show a user."""


def _paced(url: str, request):
    global _pacer
    with _pacer_lock:
        if _pacer is None:
            _pacer = host_pacing.HostPacer(host_pacing.HOST_SPACING_SECONDS)
        pacer = _pacer
    return pacer.run(url, request)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def _load_robots(origin: str) -> tuple[RobotFileParser, bool]:
    """The host's robots rules, and whether they are worth caching."""
    parser = RobotFileParser()
    robots_url = origin + "/robots.txt"
    try:
        resp = _paced(
            robots_url,
            lambda: requests.get(robots_url, headers=_HEADERS, timeout=_TIMEOUT),
        )
    except requests.RequestException as exc:
        # an unreachable robots.txt proves nothing; skip the host this time only
        logger.info("robots.txt unreachable for %s: %s", origin, exc)
        parser.disallow_all = True
        return parser, False
    status = resp.status_code
    if status in (401, 403):
        parser.disallow_all = True
    elif 400 <= status < 500:
        parser.allow_all = True
    elif status >= 500:
        parser.disallow_all = True
        return parser, False
    else:
        parser.parse(resp.text.splitlines())
    return parser, True


def robots_allows(url: str) -> bool:
    origin = _origin(url)
    now = time.monotonic()
    with _robots_lock:
        cached = _robots.get(origin)
    if cached is None or now - cached[1] > _ROBOTS_TTL_S:
        parser, cacheable = _load_robots(origin)
        if cacheable:
            with _robots_lock:
                _robots[origin] = (parser, now)
    else:
        parser = cached[0]
    return parser.can_fetch(ROBOTS_AGENT, url)


def clear_robots_cache() -> None:
    with _robots_lock:
        _robots.clear()


def _fetch(url: str, send) -> requests.Response:
    if not robots_allows(url):
        raise FetchError("That site's robots.txt asks tools not to read this page.")
    try:
        resp = _paced(url, send)
    except requests.RequestException as exc:
        logger.info("fetch failed for %s: %s", url, exc)
        raise FetchError("Could not reach that page.") from exc
    if resp.status_code != 200:
        raise FetchError(f"That page answered {resp.status_code}, not a page we can read.")
    return resp


def fetch_html(url: str) -> str:
    """The page's HTML. Raises FetchError with a user-facing reason."""
    resp = _fetch(url, lambda: requests.get(url, headers=_HEADERS, timeout=_TIMEOUT))
    return resp.text or ""


def fetch_json(url: str, body: dict | None = None):
    """A job board API's JSON: GET, or POST when ``body`` is given. Same
    robots.txt check and host pacing as fetch_html."""
    headers = {**_HEADERS, "Accept": "application/json"}

    def send() -> requests.Response:
        if body is None:
            return requests.get(url, headers=headers, timeout=_TIMEOUT)
        return requests.post(url, json=body, headers=headers, timeout=_TIMEOUT)

    resp = _fetch(url, send)
    try:
        return resp.json()
    except ValueError as exc:
        raise FetchError("That job board answered with something other than job data.") from exc
