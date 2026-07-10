"""The scrape run log: every fetch leaves a record, health reads it.

A source that silently breaks (site redesign returning 0 rows, a soft
block, a hang) looks exactly like a quiet day unless every run is
recorded. run_scrapers writes one row per source per fetch; verdicts
compare the latest run against the source's own recent history.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
BACKEND_PATH = str(ROOT / "backend")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from job_finder.source_health import verdict_for  # noqa: E402


class TestVerdicts:
    def test_healthy_volume_is_ok(self) -> None:
        assert verdict_for("ok", 40, 38) == "ok"

    def test_zero_rows_with_history_is_the_silent_breakage_signature(self) -> None:
        assert verdict_for("zero_rows", 0, 38) == "zero_rows"

    def test_zero_rows_without_history_is_honest_quiet(self) -> None:
        assert verdict_for("zero_rows", 0, 0) == "quiet"

    def test_half_the_median_is_dropped(self) -> None:
        assert verdict_for("ok", 10, 40) == "dropped"

    def test_drop_rule_ignores_thin_sources(self) -> None:
        # a 3-row source dipping to 1 is noise, not a redesign
        assert verdict_for("ok", 1, 3) == "ok"

    def test_exception_and_timeout_are_failing(self) -> None:
        assert verdict_for("exception", 0, 40) == "failing"
        assert verdict_for("timeout", 0, 40) == "failing"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import importlib

    for module_name in list(sys.modules):
        if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
            sys.modules.pop(module_name, None)
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(tmp_path / "run_log.db"))
    yield jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def test_run_scrapers_records_one_row_per_source(db, monkeypatch) -> None:
    import importlib

    # the scrapers package binds `_registry` to the registry DICT in its
    # __init__, shadowing the submodule; import_module reaches the module
    _registry = importlib.import_module("job_finder.tools.scrapers._registry")

    @_registry.register_scraper(
        name="_test_finds", display_name="Test Finds", url="https://x", vertical="career",
    )
    def _finds(**_kwargs):
        return [
            {"title": "One", "company": "A", "url": "https://x/1", "source": "_test_finds"},
            {"title": "Two", "company": "B", "url": "https://x/2", "source": "_test_finds"},
        ]

    @_registry.register_scraper(
        name="_test_breaks", display_name="Test Breaks", url="https://x", vertical="career",
    )
    def _breaks(**_kwargs):
        raise RuntimeError("site redesigned, selector gone")

    try:
        jobs = _registry.run_scrapers(names=["_test_finds", "_test_breaks"], roles=["any"])
        assert len(jobs) == 2

        runs = db.get_recent_scrape_runs(days=1)
        by_source = {r.source: r for r in runs}
        assert by_source["_test_finds"].finish_reason == "ok"
        assert by_source["_test_finds"].rows_found == 2
        assert by_source["_test_breaks"].finish_reason == "exception"
        assert by_source["_test_breaks"].rows_found == 0
        assert "selector gone" in by_source["_test_breaks"].error_sample
    finally:
        _registry._REGISTRY.pop("_test_finds", None)
        _registry._REGISTRY.pop("_test_breaks", None)


def test_source_health_reads_the_log_worst_first(db) -> None:
    from job_finder.source_health import source_health

    now = datetime.utcnow()
    rows = []
    # steady source: 30-ish rows daily, still healthy
    for i in range(6):
        rows.append({"source": "steady", "rows_found": 30 + i, "started_at": now - timedelta(days=i + 1)})
    rows.append({"source": "steady", "rows_found": 29, "started_at": now})
    # broken source: healthy history, latest run found nothing
    for i in range(6):
        rows.append({"source": "went_dark", "rows_found": 25, "started_at": now - timedelta(days=i + 1)})
    rows.append(
        {"source": "went_dark", "rows_found": 0, "finish_reason": "zero_rows", "started_at": now}
    )
    db.record_scrape_runs(rows)

    health = {h.source: h for h in source_health(days=14)}
    assert health["steady"].verdict == "ok"
    assert health["went_dark"].verdict == "zero_rows"
    assert health["went_dark"].median_rows == 25
    # worst verdicts sort first so triage reads top-down
    ordered = [h.source for h in source_health(days=14)]
    assert ordered.index("went_dark") < ordered.index("steady")


def test_record_scrape_runs_never_raises_without_a_db(monkeypatch) -> None:
    import importlib

    for module_name in list(sys.modules):
        if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
            sys.modules.pop(module_name, None)
    jf_db = importlib.import_module("job_finder.models.database")

    def _boom():
        raise RuntimeError("no db")

    monkeypatch.setattr(jf_db, "get_session", _boom)
    jf_db.record_scrape_runs([{"source": "x", "rows_found": 1}])  # must not raise
