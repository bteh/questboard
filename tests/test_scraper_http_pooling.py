"""ATS fan-out must reuse connections instead of opening one per company.

Real failure, 2026-07-27: Ashby fans out to ~816 company boards, all on
api.ashbyhq.com. ``_get_json`` called ``requests.get`` directly, so every one
of those opened a fresh TCP+TLS connection, and the host started refusing them:

    Failed to fetch https://api.ashbyhq.com/posting-api/job-board/bestow:
    Max retries exceeded (Caused by NewConnectionError(... [Errno 61]
    Connection refused))

386 of 397 failed fetches were that error, and Ashby returned 139-469 rows run
to run instead of a stable set. Widening the worker pool made it worse, because
more workers meant more simultaneous fresh connections.

A pooled session fixes it at the choke point every scraper already shares. The
pool has to be at least as wide as the fan-out, or urllib3 discards and reopens
connections under load and the problem comes back in a quieter form.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers._utils import (  # noqa: E402
    ATS_FETCH_WORKERS,
    _get_json,
    _session,
)


class _Resp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        import requests

        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} Error")
            err.response = self
            raise err


def test_fetches_go_through_one_shared_session() -> None:
    """Not ``requests.get``: that opens (and drops) a connection every call."""
    session = _session()
    with patch.object(session, "get") as mock_get:
        mock_get.return_value.json.return_value = {"jobs": []}
        mock_get.return_value.raise_for_status.return_value = None
        for i in range(5):
            _get_json(f"https://api.ashbyhq.com/posting-api/job-board/co{i}")
    assert mock_get.call_count == 5, "every fetch should use the shared session"


def test_the_same_session_object_is_reused_across_calls() -> None:
    assert _session() is _session()


def test_connection_pool_is_at_least_as_wide_as_the_fan_out() -> None:
    """A pool narrower than the worker count thrashes: urllib3 discards the
    overflow connection and the next request has to open a new one."""
    adapter = _session().get_adapter("https://api.ashbyhq.com")
    assert adapter._pool_maxsize >= ATS_FETCH_WORKERS, (
        f"pool holds {adapter._pool_maxsize} connections but {ATS_FETCH_WORKERS} "
        "workers fan out at once"
    )
    # Several ATS scrapers run at the same time, each against its own host.
    assert adapter._pool_connections >= 4


def test_a_failed_fetch_still_returns_none_rather_than_raising() -> None:
    """Pooling must not change the contract: one bad board is not fatal."""
    import requests

    session = _session()
    with patch.object(session, "get", side_effect=requests.ConnectionError("refused")):
        assert _get_json("https://api.ashbyhq.com/posting-api/job-board/nope") is None


# ── rate limits are a pause, not a dead board ───────────────────────────────

def test_a_429_is_retried_and_then_succeeds() -> None:
    """Workable answered 429 for 155 of ~410 boards under a wide fan-out and
    every one of those companies was silently dropped. Honoring the pause
    recovers them."""
    import requests

    throttled = _Resp(429, headers={"Retry-After": "0"})
    ok = _Resp(200, payload={"jobs": [{"title": "Data Engineer"}]})
    session = _session()
    with patch.object(session, "get", side_effect=[throttled, ok]) as mock_get:
        with patch("job_finder.tools.scrapers._utils.time.sleep") as sleep:
            result = _get_json("https://apply.workable.com/api/v1/widget/accounts/co")
    assert result == {"jobs": [{"title": "Data Engineer"}]}
    assert mock_get.call_count == 2
    sleep.assert_called_once()
    assert requests  # keeps the import meaningful for readers


def test_a_persistent_429_gives_up_instead_of_stalling_the_run() -> None:
    session = _session()
    throttled = [_Resp(429, headers={"Retry-After": "0"}) for _ in range(6)]
    with patch.object(session, "get", side_effect=throttled) as mock_get:
        with patch("job_finder.tools.scrapers._utils.time.sleep"):
            assert _get_json("https://apply.workable.com/api/v1/widget/accounts/co") is None
    # the first try plus a bounded number of retries, not all six
    assert mock_get.call_count == 3


def test_a_rude_retry_after_cannot_stall_the_run() -> None:
    from job_finder.tools.scrapers._utils import _RATE_LIMIT_MAX_WAIT, _retry_after_seconds

    assert _retry_after_seconds(_Resp(429, headers={"Retry-After": "3600"}), 1) == _RATE_LIMIT_MAX_WAIT


def test_a_404_reports_its_status_so_the_slug_can_be_pruned() -> None:
    seen = []
    session = _session()
    with patch.object(session, "get", return_value=_Resp(404)):
        _get_json("https://api.lever.co/v0/postings/ghostco", on_status=seen.append)
    assert seen == [404]


def test_a_refused_connection_reports_no_status() -> None:
    """None, not a number: the caller must not read this as 'board is gone'."""
    import requests

    seen = []
    session = _session()
    with patch.object(session, "get", side_effect=requests.ConnectionError("refused")):
        _get_json("https://api.ashbyhq.com/posting-api/job-board/realco", on_status=seen.append)
    assert seen == [None]
