"""Asking each ATS whether a cached company board still exists.

`sweep_dead_slugs` takes a probe rather than building one, because the URL of
a company's board belongs to that host's scraper and must not be written down
twice. This is the other half: turning each scraper's own per-board fetch into
a probe.

The trap this module exists to avoid: every scraper's fetch returns an empty
list for a board that 404s AND for a healthy board with nothing matching the
roles you asked about. A probe reading the return value would call most of a
live cache dead. Only the HTTP status separates the two, which is why every
scraper takes an `on_status` hook and why the probe reads that instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers import _board_probe  # noqa: E402
from job_finder.tools.scrapers._ats_discovery import ATS_HOSTS  # noqa: E402


@pytest.fixture()
def answer(monkeypatch):
    """Stub the shared HTTP layer and let a test dictate what a board answers."""

    def _install(status, payload=None, raises=None):
        def fake_get_json(url, *args, on_status=None, **kwargs):
            if raises is not None:
                raise raises
            if on_status is not None:
                on_status(status)
            return payload

        for name in _board_probe.PROBES:
            module = _board_probe._scraper_module(name)
            monkeypatch.setattr(module, "_get_json", fake_get_json)

    return _install


def test_every_discoverable_host_can_be_probed():
    """A host discovery caches but nothing can probe would keep its dead slugs
    forever with no sign anything was wrong."""
    assert set(_board_probe.PROBES) == set(ATS_HOSTS)


@pytest.mark.parametrize("host", sorted(ATS_HOSTS))
def test_a_missing_board_probes_as_404(host, answer):
    answer(404, payload=None)
    assert _board_probe.probe_status(host)("ghostco") == 404


@pytest.mark.parametrize("host", sorted(ATS_HOSTS))
def test_a_live_board_probes_as_200(host, answer):
    answer(200, payload={"jobs": [], "data": [], "results": []})
    assert _board_probe.probe_status(host)("realco") == 200


def test_a_live_board_with_no_matching_jobs_is_not_dead(answer):
    """The whole reason the probe reads status and not the returned rows.

    Ashby has 247 cached slugs and a probe asks about no particular role, so
    nearly every one of them returns zero jobs. Judging by the list would have
    pruned the entire cache.
    """
    answer(200, payload={"jobs": []})
    assert _board_probe.probe_status("ashby")("realco") == 200


def test_a_board_that_raises_reports_no_status(answer):
    """Connection refused, DNS failure, timeout. Unreachable is not dead."""
    answer(None, raises=OSError("[Errno 61] Connection refused"))
    assert _board_probe.probe_status("ashby")("flakyco") is None


def test_an_unknown_host_is_refused_loudly(answer):
    with pytest.raises(KeyError):
        _board_probe.probe_status("bamboohr")
