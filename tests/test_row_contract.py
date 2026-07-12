"""The row contract: a listing publishes only when it is actionable.

Every check here maps to a real failure that reached the live board on
2026-07-10 (docs/source-coverage.md): a blog article as a casting call,
"[ Removed by moderator ]" as a title, reddit discussion threads as the
way to act. The contract turns each one from an incident into a counted,
visible reject.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.row_contract import validate_row, validate_rows  # noqa: E402

NOW = datetime(2026, 7, 10, 12, 0, 0)


@dataclass
class FakeMeta:
    allowed_url_hosts: tuple[str, ...] | None = None
    allowed_url_paths: tuple[str, ...] | None = None


def _row(**over) -> dict:
    base = {
        "title": "Casting call for real golfers",
        "url": "https://projectcasting.com/job/slip-casting-call",
        "date_posted": "2026-07-08",
    }
    base.update(over)
    return base


class TestSharedRules:
    def test_a_clean_row_passes(self) -> None:
        assert validate_row(_row(), FakeMeta(), NOW) is None

    def test_moderation_placeholder_titles_never_publish(self) -> None:
        # "[ Removed by moderator ]" reached the live board on 2026-07-10
        for title in ("[removed]", "[ Removed by moderator ]", "[deleted]", "removed"):
            assert validate_row(_row(title=title), FakeMeta(), NOW) == "placeholder_title", title

    def test_empty_title_never_publishes(self) -> None:
        assert validate_row(_row(title="  "), FakeMeta(), NOW) == "missing_title"

    def test_malformed_url_never_publishes(self) -> None:
        assert validate_row(_row(url="not a url"), FakeMeta(), NOW) == "malformed_url"
        assert validate_row(_row(url="ftp://weird.example/x"), FakeMeta(), NOW) == "malformed_url"

    def test_future_post_dates_are_fiction(self) -> None:
        assert validate_row(_row(date_posted="2026-08-01"), FakeMeta(), NOW) == "future_date"
        # a day of slack for timezone edges
        assert validate_row(_row(date_posted="2026-07-11"), FakeMeta(), NOW) is None

    def test_unparseable_dates_pass_shared_rules(self) -> None:
        # freshness filters already treat unverifiable dates honestly;
        # the contract only rejects provable fiction
        assert validate_row(_row(date_posted="last Tuesday"), FakeMeta(), NOW) is None


class TestDeclaredGates:
    META = FakeMeta(
        allowed_url_hosts=("projectcasting.com",),
        allowed_url_paths=("/job/",),
    )

    def test_the_blog_leak_dies_at_the_path_gate(self) -> None:
        # the exact 2026-07-10 incident: /blog/ published as a casting call
        row = _row(url="https://projectcasting.com/blog/casting-scam-alert")
        assert validate_row(row, self.META, NOW) == "path_not_allowed"

    def test_foreign_hosts_die_at_the_host_gate(self) -> None:
        # a reddit thread is never the way to act for a gated source
        row = _row(url="https://www.reddit.com/r/PKMNTCGDeals/comments/1td/x/")
        assert validate_row(row, self.META, NOW) == "host_not_allowed"

    def test_subdomains_of_the_declared_host_pass(self) -> None:
        row = _row(url="https://www.projectcasting.com/job/slip-casting-call")
        assert validate_row(row, self.META, NOW) is None

    def test_lookalike_hosts_fail(self) -> None:
        row = _row(url="https://evilprojectcasting.com/job/slip-casting-call")
        assert validate_row(row, self.META, NOW) == "host_not_allowed"

    def test_gated_sources_must_state_a_url(self) -> None:
        assert validate_row(_row(url=""), self.META, NOW) == "missing_url"

    def test_ungated_sources_may_point_anywhere(self) -> None:
        # bankrewards points at each bank's own offer page by design
        row = _row(url="https://promotions.bankofamerica.com/offer")
        assert validate_row(row, FakeMeta(), NOW) is None


class TestValidateRows:
    def test_splits_and_reports_reasons(self) -> None:
        meta = FakeMeta(allowed_url_hosts=("clinicaltrials.gov",), allowed_url_paths=("/study/",))
        rows = [
            _row(url="https://clinicaltrials.gov/study/NCT001"),
            _row(title="[removed]", url="https://clinicaltrials.gov/study/NCT002"),
            _row(url="https://clinicaltrials.gov/about"),
        ]
        valid, rejected = validate_rows(rows, meta, NOW)
        assert len(valid) == 1
        assert [reason for _, reason in rejected] == ["placeholder_title", "path_not_allowed"]


class TestRegistryContracts:
    # Sources whose rows point OUTWARD at many legitimate hosts by
    # design, so a host gate is impossible; each validates https itself
    # and documents the reasoning in its module docstring. A new
    # hosts=None source fails this test until deliberately added here.
    OUTWARD_SOURCES = {
        "bankrewards",        # rows land on each bank's own offer page
        "callingallpapers",   # submission links span sessionize + one-off conference hosts
        "cagrants",           # GrantURLs span many *.ca.gov subdomains + vendor hosts
    }

    def test_every_schedulable_source_declares_where_its_rows_point(self) -> None:
        from job_finder.schedule import schedulable_metas

        for meta in schedulable_metas():
            if meta.name in self.OUTWARD_SOURCES:
                assert meta.allowed_url_hosts is None, meta.name
                continue
            assert meta.allowed_url_hosts, f"{meta.name} declares no allowed_url_hosts"

    def test_run_scrapers_drops_invalid_rows_and_counts_them(self, monkeypatch, tmp_path) -> None:
        import importlib

        for module_name in list(sys.modules):
            if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
                sys.modules.pop(module_name, None)
        jf_db = importlib.import_module("job_finder.models.database")
        jf_db.init_db(str(tmp_path / "contract.db"))

        _registry = importlib.import_module("job_finder.tools.scrapers._registry")

        def fake_search(**kw):
            return [
                {"title": "Real study", "url": "https://clinicaltrials.gov/study/NCT001",
                 "company": "X", "source": "contract_probe", "vertical": "body"},
                {"title": "[ Removed by moderator ]",
                 "url": "https://clinicaltrials.gov/study/NCT002",
                 "company": "X", "source": "contract_probe", "vertical": "body"},
                {"title": "About page leak", "url": "https://clinicaltrials.gov/about",
                 "company": "X", "source": "contract_probe", "vertical": "body"},
            ]

        _registry._REGISTRY["contract_probe"] = _registry.ScraperMeta(
            name="contract_probe", display_name="Contract Probe", url="",
            description="", category="", enabled_by_default=False,
            search_fn=fake_search, vertical="body",
            allowed_url_hosts=("clinicaltrials.gov",),
            allowed_url_paths=("/study/",),
        )
        try:
            rows = _registry.run_scrapers(names=["contract_probe"], max_results=10)
            assert len(rows) == 1
            assert rows[0]["title"] == "Real study"

            runs = jf_db.get_recent_scrape_runs(source="contract_probe")
            assert len(runs) == 1
            assert runs[0].rows_found == 1
            assert runs[0].rows_invalid == 2
        finally:
            _registry._REGISTRY.pop("contract_probe", None)
            if jf_db._SessionLocal is not None:
                jf_db._SessionLocal.remove()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
