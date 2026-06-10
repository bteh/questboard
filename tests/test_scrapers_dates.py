"""Posting-date accuracy for ATS scrapers (Lever / Greenhouse / Ashby).

Lever used to hardcode ``date_posted=''`` even though its postings API
returns ``createdAt`` (epoch ms), and Greenhouse used ``updated_at`` so a
year-old job edited yesterday looked new — both let stale jobs bypass the
freshness filter. These tests pin:

- ``date_posted`` populated from the API's real posting timestamp and
  parseable by the pipeline's ``_parse_posted_date``
- ``date_confidence`` stamped per the shared contract:
  'exact' (real posting date) | 'fuzzy' (updated/approx only) | 'missing'
- the shared ``_utils`` post-processing path defaults the field so every
  scraper job dict carries it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

FIXTURES = Path(__file__).parent / "fixtures"

from job_finder.tools.scrapers._utils import _parse_posted_date  # noqa: E402


def _load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── Lever ─────────────────────────────────────────────────────────────────────

def test_lever_date_posted_from_created_at(monkeypatch):
    from job_finder.tools.scrapers import lever

    payload = _load_fixture("lever_postings.json")
    monkeypatch.setattr(lever, "_get_json", lambda *a, **k: payload)
    jobs = lever._fetch_company_postings(
        "acme", ["data engineer"], match_mode="all_significant", include_founding=True,
    )
    assert len(jobs) == 2
    by_url = {j["url"]: j for j in jobs}

    dated = by_url["https://jobs.lever.co/acme/1"]
    # createdAt epoch ms must flow through, not a hardcoded ''
    assert dated["date_posted"] == 1749340800000
    parsed = _parse_posted_date(dated["date_posted"])
    assert parsed == datetime(2025, 6, 8, tzinfo=timezone.utc)
    assert dated["date_confidence"] == "exact"

    undated = by_url["https://jobs.lever.co/acme/2"]
    assert _parse_posted_date(undated["date_posted"]) is None
    assert undated["date_confidence"] == "missing"


# ── Greenhouse ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url, expected_date, expected_confidence",
    [
        # first_published preferred over updated_at -> exact
        ("https://boards.greenhouse.io/acme/jobs/1", "2026-05-20T12:00:00-04:00", "exact"),
        # only updated_at available -> fuzzy
        ("https://boards.greenhouse.io/acme/jobs/2", "2026-06-09T08:00:00-04:00", "fuzzy"),
        # neither -> missing
        ("https://boards.greenhouse.io/acme/jobs/3", "", "missing"),
    ],
)
def test_greenhouse_date_confidence(monkeypatch, url, expected_date, expected_confidence):
    from job_finder.tools.scrapers import greenhouse

    payload = _load_fixture("greenhouse_jobs.json")
    monkeypatch.setattr(greenhouse, "_get_json", lambda *a, **k: payload)
    jobs = greenhouse._fetch_company_jobs(
        "acme", ["data engineer"], match_mode="all_significant", include_founding=True,
    )
    by_url = {j["url"]: j for j in jobs}
    job = by_url[url]
    assert job["date_posted"] == expected_date
    assert job["date_confidence"] == expected_confidence
    if expected_confidence != "missing":
        assert _parse_posted_date(job["date_posted"]) is not None


def test_greenhouse_prefers_first_published_over_updated_at(monkeypatch):
    """A year-old job edited yesterday must NOT look freshly posted."""
    from job_finder.tools.scrapers import greenhouse

    payload = {
        "jobs": [{
            "title": "Data Engineer",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/old/jobs/9",
            "content": "old job",
            "first_published": "2025-06-01T00:00:00Z",
            "updated_at": "2026-06-09T00:00:00Z",
        }]
    }
    monkeypatch.setattr(greenhouse, "_get_json", lambda *a, **k: payload)
    jobs = greenhouse._fetch_company_jobs("old", ["data engineer"])
    assert len(jobs) == 1
    parsed = _parse_posted_date(jobs[0]["date_posted"])
    assert parsed == datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert jobs[0]["date_confidence"] == "exact"


# ── Ashby ─────────────────────────────────────────────────────────────────────

def test_ashby_date_confidence(monkeypatch):
    from job_finder.tools.scrapers import ashby

    payload = {
        "jobs": [
            {
                "title": "Data Engineer",
                "location": "Remote",
                "jobUrl": "u1",
                "publishedAt": "2026-06-01T00:00:00.000Z",
            },
            {
                "title": "Senior Data Engineer",
                "location": "Remote",
                "jobUrl": "u2",
            },
        ]
    }
    monkeypatch.setattr(ashby, "_get_json", lambda *a, **k: payload)
    jobs = ashby._fetch_company_jobs("acme", ["data engineer"])
    by_url = {j["url"]: j for j in jobs}
    assert by_url["u1"]["date_confidence"] == "exact"
    assert _parse_posted_date(by_url["u1"]["date_posted"]) is not None
    assert by_url["u2"]["date_confidence"] == "missing"


# ── Shared post-processing path ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "job, expected",
    [
        ({"title": "a", "date_posted": "2026-06-01"}, "exact"),
        ({"title": "b", "date_posted": 1749340800000}, "exact"),
        ({"title": "c", "date_posted": ""}, "missing"),
        ({"title": "d"}, "missing"),
        ({"title": "e", "date_posted": "not a date"}, "missing"),
        # an explicit scraper-stamped value is never overwritten
        ({"title": "f", "date_posted": "2026-06-01", "date_confidence": "fuzzy"}, "fuzzy"),
    ],
)
def test_finalize_defaults_date_confidence(job, expected):
    from job_finder.tools.scrapers._utils import finalize_scraper_jobs

    out = finalize_scraper_jobs([dict(job)])
    assert out[0]["date_confidence"] == expected


def test_run_scrapers_stamps_contract_fields():
    """Every job dict leaving run_scrapers carries the contract fields."""
    from job_finder.tools.scrapers._registry import register_scraper, run_scrapers

    @register_scraper(
        name="_test_dates_fake",
        display_name="TestDatesFake",
        url="https://example.com",
    )
    def _fake(**kwargs):
        return [{"title": "x", "company": "y", "url": "u", "source": "_test_dates_fake"}]

    jobs = run_scrapers(names=["_test_dates_fake"], roles=None)
    assert len(jobs) == 1
    assert jobs[0]["date_confidence"] == "missing"
    assert jobs[0].get("salary_source") is None
    assert jobs[0]["work_type_confidence"] == "inferred"
