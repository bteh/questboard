"""Freshness filter must honor date_confidence under the strict preset.

Before: ``_filter_jobs_by_freshness`` kept ANY job whose date_posted was
missing or unparseable — so under a strict search a stale, undateable
reposting always slipped through. Now that scrapers stamp
``date_confidence`` ('exact'|'fuzzy'|'missing'), the strict preset drops
jobs with no verifiable date while loose/balanced keep the old
keep-on-uncertainty behavior.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from job_finder.pipeline import _filter_jobs_by_freshness, _resolve_filter_settings

NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _job(date_posted, **extra):
    return {"title": "Engineer", "url": "u", "date_posted": date_posted, **extra}


# ── real dates still gate, regardless of confidence plumbing ────────────────

def test_90_day_old_epoch_ms_dropped_at_14_days() -> None:
    ms = int((NOW - timedelta(days=90)).timestamp() * 1000)
    out = _filter_jobs_by_freshness([_job(ms)], max_days_old=14, now=NOW)
    assert out == []


def test_fresh_epoch_ms_kept_at_14_days() -> None:
    ms = int((NOW - timedelta(days=3)).timestamp() * 1000)
    out = _filter_jobs_by_freshness([_job(ms)], max_days_old=14, now=NOW)
    assert len(out) == 1


# ── date_confidence='missing' under strict vs loose ─────────────────────────

def test_missing_confidence_dropped_when_strict() -> None:
    job = _job(None, date_confidence="missing")
    out = _filter_jobs_by_freshness(
        [job], max_days_old=14, now=NOW, drop_missing_dates=True
    )
    assert out == []


def test_missing_confidence_kept_by_default() -> None:
    job = _job(None, date_confidence="missing")
    out = _filter_jobs_by_freshness([job], max_days_old=14, now=NOW)
    assert len(out) == 1


def test_unstamped_job_with_no_date_treated_as_missing_when_strict() -> None:
    # Jobs that never passed through finalize_scraper_jobs carry no
    # date_confidence key — an absent/unparseable date means 'missing'.
    out = _filter_jobs_by_freshness(
        [_job(""), _job("recently")], max_days_old=14, now=NOW,
        drop_missing_dates=True,
    )
    assert out == []


def test_exact_confidence_fresh_job_kept_when_strict() -> None:
    recent = (NOW - timedelta(days=2)).strftime("%Y-%m-%d")
    job = _job(recent, date_confidence="exact")
    out = _filter_jobs_by_freshness(
        [job], max_days_old=14, now=NOW, drop_missing_dates=True
    )
    assert len(out) == 1


# ── preset wiring ────────────────────────────────────────────────────────────

def test_strict_preset_enables_drop_missing_dates() -> None:
    settings = _resolve_filter_settings({"filters": {"strictness": "strict"}})
    assert settings["drop_missing_dates"] is True


def test_loose_and_balanced_presets_keep_missing_dates() -> None:
    for strictness in ("loose", "balanced"):
        settings = _resolve_filter_settings({"filters": {"strictness": strictness}})
        assert settings["drop_missing_dates"] is False, strictness


def test_drop_missing_dates_overridable_per_key() -> None:
    settings = _resolve_filter_settings(
        {"filters": {"strictness": "strict", "drop_missing_dates": False}}
    )
    assert settings["drop_missing_dates"] is False
