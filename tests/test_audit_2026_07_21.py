"""Audit 2026-07-21: salary integrity (S1-S4) and description quality (D1-D5).

S1 - currency dropped (Ashby currencyCode, EUR/GBP symbols in parsed text)
S2 - hourly pay fabricated into annual (raw + salary_period contract)
S3 - salary floor filter drops hourly roles
S4 - ATS structured pay provenance must survive to the DB / MCP payload
D1 - entity-encoded HTML survives _strip_html
D2 - MCP excerpt served raw and cut mid-word
D3 - builtin list cards store empty descriptions
D5 - builtin stores fuzzy date prose instead of a real date
MINOR - MCP retrieval bucket/method say 'unclassified' for never-ranked rows
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)

from job_finder.tools.scrapers._utils import (  # noqa: E402
    _parse_posted_date,
    _strip_html,
    extract_salary_range,
    finalize_scraper_jobs,
)


# ── S1: currency ─────────────────────────────────────────────────────────────

_ASHBY_BOARD = {
    "jobs": [
        {
            "title": "Data Engineer",
            "location": "Remote",
            "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/acme/1",
            "descriptionPlain": "Build pipelines.",
            "publishedAt": "2026-07-20T00:00:00Z",
            "compensation": {
                "compensationTiers": [
                    {
                        "components": [
                            {
                                "compensationType": "Salary",
                                "interval": "1 YEAR",
                                "currencyCode": "USD",
                                "minValue": 150000,
                                "maxValue": 180000,
                            }
                        ]
                    }
                ]
            },
        },
        {
            "title": "Data Engineer Contractor",
            "location": "Remote",
            "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/acme/2",
            "descriptionPlain": "Hourly contract.",
            "publishedAt": "2026-07-20T00:00:00Z",
            "compensation": {
                "compensationTiers": [
                    {
                        "components": [
                            {
                                "compensationType": "Salary",
                                "interval": "1 HOUR",
                                "currencyCode": "USD",
                                "minValue": 45,
                                "maxValue": 55,
                            }
                        ]
                    }
                ]
            },
        },
    ]
}


def _fetch_ashby_jobs():
    from job_finder.tools.scrapers import ashby

    with patch.object(ashby, "_get_json", return_value=_ASHBY_BOARD):
        return ashby._fetch_company_jobs("acme", ["Data Engineer"])


def test_s1_ashby_captures_currency_code():
    jobs = {j["url"]: j for j in _fetch_ashby_jobs()}
    annual = jobs["https://jobs.ashbyhq.com/acme/1"]
    assert annual["salary_currency"] == "USD"
    assert annual["salary_min"] == 150000
    assert annual["salary_max"] == 180000


@pytest.mark.parametrize(
    "text, currency",
    [
        ("Salary: €50,000 - €70,000 per year", "EUR"),
        ("Pay: £50k-£70k", "GBP"),
        # '$' is ambiguous (USD/CAD/AUD) — no currency claim from text.
        ("$140k-$170k", None),
    ],
)
def test_s1_extractor_detects_unambiguous_currency_symbols(text, currency):
    result = extract_salary_range(text)
    assert result.salary_min is not None
    assert result.currency == currency


def test_s1_finalize_stamps_parsed_currency():
    job = {"title": "Engineer", "description": "Base pay £60,000 to £80,000."}
    out = finalize_scraper_jobs([job])[0]
    assert out["salary_currency"] == "GBP"
    assert out["salary_min"] == 60000.0


# ── S2: hourly pay must stay hourly ──────────────────────────────────────────

def test_s2_extractor_returns_raw_hourly_and_period():
    result = extract_salary_range("Pay range: $40 - $50 per hour")
    assert (result.salary_min, result.salary_max) == (40.0, 50.0)
    assert result.period == "hourly"

    single = extract_salary_range("$45/hr")
    assert (single.salary_min, single.salary_max) == (45.0, None)
    assert single.period == "hourly"

    annual = extract_salary_range("$140,000 to $170,000 annually")
    assert (annual.salary_min, annual.salary_max) == (140000.0, 170000.0)
    assert annual.period == "annual"


def test_s2_finalize_puts_annualized_values_in_annualized_fields():
    job = {"title": "Engineer", "description": "Pay range: $40 - $50 per hour"}
    out = finalize_scraper_jobs([job])[0]
    assert out["salary_min"] == 40.0  # raw, not fabricated annual
    assert out["salary_max"] == 50.0
    assert out["salary_period"] == "hourly"
    assert out["salary_min_annualized"] == 40.0 * 2080
    assert out["salary_max_annualized"] == 50.0 * 2080
    assert out["salary_source"] == "parsed_from_description"


def test_s2_ashby_reads_comp_interval():
    jobs = {j["url"]: j for j in _fetch_ashby_jobs()}
    hourly = jobs["https://jobs.ashbyhq.com/acme/2"]
    assert hourly["salary_period"] == "hourly"
    assert hourly["salary_min"] == 45  # raw hourly rate
    annual = jobs["https://jobs.ashbyhq.com/acme/1"]
    assert annual["salary_period"] == "annual"
    # finalize (run_scrapers post-processing) annualizes the hourly rate
    finalized = finalize_scraper_jobs(list(jobs.values()))
    hourly = next(j for j in finalized if j["url"].endswith("/2"))
    assert hourly["salary_min_annualized"] == 45 * 2080


_BUILTIN_HOURLY_CARD = """
<div data-id="job-card">
  <a data-id="job-card-title" href="/job/data-engineer/1">Data Engineer</a>
  <div data-id="company-title"><span>Acme</span></div>
  <div><i class="fa fa-location-dot"></i><span>Los Angeles, CA</span></div>
  <div><i class="fa fa-sack-dollar"></i><span>$50/hr</span></div>
  <span>Posted 2 Days Ago</span>
</div>
"""


def test_s2_builtin_hourly_rate_not_multiplied_into_50000():
    from job_finder.tools.scrapers.builtin import _parse_html_jobs

    rows = _parse_html_jobs(_BUILTIN_HOURLY_CARD, ["Data Engineer"], 10)
    assert rows, "card should parse"
    job = rows[0]
    assert job["salary_min"] == 50.0  # NOT 50000 via the x1000 heuristic
    assert job["salary_max"] is None
    assert job["salary_period"] == "hourly"


# ── S3: salary floor must annualize hourly values ────────────────────────────

def test_s3_hourly_job_passes_annual_floor():
    from job_finder.pipeline import _job_salary_passes

    # $40-$50/hr -> ~93.6k-104k annual; must clear a 60k floor.
    job = {"salary_min": 40.0, "salary_max": 50.0, "salary_period": "hourly"}
    assert _job_salary_passes(job, 60000)

    # ...and still fail a floor it genuinely misses once annualized.
    job_low = {"salary_max": 50.0, "salary_period": "hourly"}
    assert not _job_salary_passes(job_low, 150000)


def test_s3_obviously_hourly_values_annualized_without_period():
    from job_finder.pipeline import _job_salary_passes

    # No period marker but 50 can't be an annual salary — treat as hourly.
    assert _job_salary_passes({"salary_max": 50.0}, 60000)


# ── S4: provenance persists end-to-end ───────────────────────────────────────

def test_s4_ashby_structured_pay_is_reported():
    jobs = _fetch_ashby_jobs()
    for job in jobs:
        assert job["salary_source"] == "reported"


def test_s4_search_only_save_persists_salary_provenance(tmp_path, monkeypatch):
    db_file = tmp_path / "job_tracker.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    from job_finder.models import database

    database.init_db(str(db_file))
    try:
        from app.services.pipeline_service import _save_search_results

        pipeline = SimpleNamespace(profile_name="default")
        _save_search_results(
            pipeline,
            [
                {
                    "title": "Data Engineer",
                    "company": "Acme",
                    "url": "https://example.com/j/1",
                    "source": "ashby",
                    "salary_min": 45.0,
                    "salary_max": 55.0,
                    "salary_currency": "USD",
                    "salary_period": "hourly",
                    "salary_min_annualized": 93600.0,
                    "salary_max_annualized": 114400.0,
                    "salary_source": "reported",
                }
            ],
            lambda msg: None,
        )
        rec = database.get_all_applications()[0]
        assert rec.salary_source == "reported"
        assert rec.salary_currency == "USD"
        assert rec.salary_period == "hourly"
        assert rec.salary_min_annualized == 93600.0
        assert rec.salary_max_annualized == 114400.0
    finally:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()


# ── D1: entity-encoded HTML must not survive stripping ───────────────────────

_GREENHOUSE_ENCODED = (
    "&lt;div class=&quot;content-intro&quot;&gt;&lt;p data-leveltext=&quot;&quot; "
    "data-font=&quot;Arial&quot; data-listid=&quot;3&quot;&gt;&lt;strong&gt;About "
    "us&lt;/strong&gt; We build data platforms.&lt;/p&gt;&lt;/div&gt;"
    "&lt;p&gt;Salary: $140k-$170k&lt;/p&gt;"
)


def test_d1_strip_html_unescapes_before_stripping():
    text = _strip_html(_GREENHOUSE_ENCODED)
    assert "<" not in text
    assert ">" not in text
    assert "content-intro" not in text
    assert "data-leveltext" not in text
    assert "About us" in text
    assert "We build data platforms." in text


def test_d1_greenhouse_description_is_clean():
    from job_finder.tools.scrapers import greenhouse

    board = {
        "jobs": [
            {
                "title": "Data Engineer",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "content": _GREENHOUSE_ENCODED,
                "first_published": "2026-07-20T00:00:00Z",
                "updated_at": "2026-07-20T00:00:00Z",
            }
        ]
    }
    with patch.object(greenhouse, "_get_json", return_value=board):
        jobs = greenhouse._fetch_company_jobs("acme", ["Data Engineer"])
    assert jobs
    assert "content-intro" not in jobs[0]["description"]
    assert "About us" in jobs[0]["description"]


# ── D2 / MINOR: MCP payload hygiene ──────────────────────────────────────────

def _make_record(**kwargs):
    from app.models.application import ApplicationRecord

    defaults = {"job_title": "Data Engineer", "company": "Acme"}
    defaults.update(kwargs)
    return ApplicationRecord(**defaults)


def test_d2_mcp_excerpt_is_clean_and_word_bounded():
    from app.services.local_agent_service import _candidate_payload

    words = ("alpha", "beta", "gamma", "delta")
    long_desc = "&lt;div class=&quot;content-intro&quot;&gt;" + " ".join(
        words[i % 4] for i in range(600)
    ) + "&lt;/div&gt;"
    payload = _candidate_payload(_make_record(description=long_desc))
    excerpt = payload["description_excerpt"]
    assert "<" not in excerpt
    assert "content-intro" not in excerpt
    assert len(excerpt) <= 1201  # 1200 + ellipsis
    assert excerpt.endswith("…")
    # No mid-word cut: the last token before the ellipsis is a whole word.
    assert excerpt[:-1].rstrip().split()[-1] in words


def test_d2_short_description_untouched():
    from app.services.local_agent_service import _candidate_payload

    payload = _candidate_payload(_make_record(description="Short and sweet."))
    assert payload["description_excerpt"] == "Short and sweet."


def test_minor_not_ranked_instead_of_unclassified():
    from app.services.local_agent_service import _candidate_payload

    payload = _candidate_payload(_make_record())
    assert payload["retrieval"]["bucket"] == "not_ranked"
    assert payload["retrieval"]["method"] == "not_ranked"


# ── D3: builtin cards synthesize an excerpt ──────────────────────────────────

def test_d3_builtin_card_description_never_empty():
    from job_finder.tools.scrapers.builtin import _parse_html_jobs

    rows = _parse_html_jobs(_BUILTIN_HOURLY_CARD, ["Data Engineer"], 10)
    desc = rows[0]["description"]
    assert desc, "list cards must synthesize a one-line excerpt"
    assert "Data Engineer" in desc
    assert "Acme" in desc


# ── D5: builtin fuzzy dates become real dates ────────────────────────────────

def _builtin_card_with_date(date_text: str) -> str:
    return f"""
    <div data-id="job-card">
      <a data-id="job-card-title" href="/job/data-engineer/9">Data Engineer</a>
      <div data-id="company-title"><span>Acme</span></div>
      <span>{date_text}</span>
    </div>
    """


def test_d5_builtin_stores_real_iso_date_for_fuzzy_prose():
    from job_finder.tools.scrapers.builtin import _parse_html_jobs

    rows = _parse_html_jobs(
        _builtin_card_with_date("Reposted 20 Days Ago"),
        ["Data Engineer"],
        10,
        max_days_old=30,
    )
    assert rows
    job = rows[0]
    parsed = _parse_posted_date(job["date_posted"])
    assert parsed is not None, f"date_posted {job['date_posted']!r} must parse"
    expected = datetime.now(timezone.utc) - timedelta(days=20)
    assert abs((parsed - expected).total_seconds()) < 86400 * 2
    assert job["date_confidence"] == "fuzzy"


@pytest.mark.parametrize(
    "prose, days",
    [
        ("Posted Today", 0),
        ("Reposted 4 Hours Ago", 0),
        ("Yesterday", 1),
        ("Posted 7 Days Ago", 7),
    ],
)
def test_d5_fuzzy_phrases_convert(prose, days):
    from job_finder.tools.scrapers.builtin import _parse_html_jobs

    rows = _parse_html_jobs(
        _builtin_card_with_date(prose), ["Data Engineer"], 10, max_days_old=30
    )
    parsed = _parse_posted_date(rows[0]["date_posted"])
    assert parsed is not None
    expected = datetime.now(timezone.utc) - timedelta(days=days)
    assert abs((parsed - expected).total_seconds()) < 86400 * 2


def test_d5_freshness_filter_applies_to_builtin_rows():
    from job_finder.pipeline import _filter_jobs_by_freshness
    from job_finder.tools.scrapers.builtin import _parse_html_jobs

    fresh = _parse_html_jobs(
        _builtin_card_with_date("Posted 2 Days Ago"), ["Data Engineer"], 10,
        max_days_old=30,
    )
    stale = _parse_html_jobs(
        _builtin_card_with_date("Reposted 25 Days Ago"), ["Data Engineer"], 10,
        max_days_old=30,
    )
    kept = _filter_jobs_by_freshness(fresh + stale, 14)
    assert len(kept) == 1, "stale builtin row must be dropped by max_days_old"


def test_d5_builtin_detail_date_is_real():
    from job_finder.tools.scrapers.builtin import fetch_builtin_detail

    detail_html = """
    <html><body>
      <div>Posted 4 Hours Ago</div>
      <div id="job-post-body-123"><p>Own the pipelines.</p></div>
    </body></html>
    """
    with patch(
        "job_finder.tools.scrapers.builtin._fetch_page", return_value=detail_html
    ):
        result = fetch_builtin_detail("https://builtin.com/job/example/123")
    assert _parse_posted_date(result["date_posted"]) is not None
    assert result["date_confidence"] == "fuzzy"
