"""Tighten cross-board dedup WITHOUT over-merging distinct openings.

Cross-board duplicates (same posting on Indeed/Glassdoor/LinkedIn) often differ
in location text or have a description on only one side, so the old company+
title+location key with a description-match requirement left them un-merged.
This relaxes the key to company+title, with a location- and description-aware
cluster predicate that still keeps genuinely distinct roles apart.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.pipeline import _deduplicate

_LONG_A = ("Own and scale the data platform end to end: design batch and streaming "
           "pipelines, lead the lakehouse migration, and mentor two engineers on it.")
_LONG_B = ("Build the consumer-facing React dashboard, own the design-system "
           "components, and partner with product on the onboarding redesign work.")


def _job(title, company, loc, desc, url, remote=False):
    return {"title": title, "company": company, "location": loc,
            "description": desc, "url": url, "is_remote": remote}


# ── MERGES (the new wins) ────────────────────────────────────────────────────
def test_merge_both_remote_one_missing_description():
    jobs = [
        _job("Senior Data Engineer", "Acme", "Remote", _LONG_A, "u1", remote=True),
        _job("Senior Data Engineer", "Acme", "Remote - US", "", "u2", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 1


def test_merge_same_location_one_missing_description():
    jobs = [
        _job("Backend Engineer", "Beta", "Austin, TX", _LONG_A, "u1"),
        _job("Backend Engineer", "Beta", "Austin, TX", "", "u2"),
    ]
    assert len(_deduplicate(jobs)) == 1


# ── GUARDS (must NOT over-merge) ─────────────────────────────────────────────
def test_keep_different_concrete_locations():
    # Same title/company in two cities = two distinct openings (even same desc).
    jobs = [
        _job("Software Engineer", "Gamma", "Austin, TX", _LONG_A, "u1"),
        _job("Software Engineer", "Gamma", "Seattle, WA", _LONG_A, "u2"),
    ]
    assert len(_deduplicate(jobs)) == 2


def test_keep_remote_vs_onsite():
    jobs = [
        _job("Designer", "Delta", "Remote", _LONG_A, "u1", remote=True),
        _job("Designer", "Delta", "Chicago, IL", _LONG_A, "u2"),
    ]
    assert len(_deduplicate(jobs)) == 2


def test_keep_same_location_different_substantial_descriptions():
    # Same title/company/location but clearly different roles (distinct long descs).
    jobs = [
        _job("Software Engineer", "Epsilon", "Remote", _LONG_A, "u1", remote=True),
        _job("Software Engineer", "Epsilon", "Remote", _LONG_B, "u2", remote=True),
    ]
    assert len(_deduplicate(jobs)) == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
