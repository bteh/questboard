"""Work-type classification accuracy (remote / hybrid / onsite).

``classify_work_type`` used to downgrade remote-flagged jobs to hybrid
whenever a city appeared in the location string unless the description
matched a narrow phrase list, so confirmations like 'this position is
remote' were missed. ATS scrapers that report a definitive remote flag
(e.g. Ashby ``isRemote``) now thread ``remote_flag_reported`` through the
job dict so the text-heuristic downgrade is skipped, and the shared
post-processing stamps ``work_type_confidence`` ('reported' | 'inferred').
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.company_classifier import classify_work_type  # noqa: E402


@pytest.mark.parametrize(
    "location, description, is_remote_hint, expected",
    [
        # location-level signals
        ("Remote (based in San Francisco)", "", False, "remote"),
        ("Remote - US", "", False, "remote"),
        ("Remote", "", True, "remote"),
        ("Hybrid - 3 days in office", "", False, "hybrid"),
        ("Remote / Hybrid in San Francisco", "", False, "hybrid"),
        ("San Francisco, CA", "", False, "onsite"),
        ("In-person, Palo Alto, CA", "", False, "onsite"),
        # board hint + bare city + no textual confirmation -> stays skeptical
        ("Durham, NC", "", True, "hybrid"),
        ("London, UK", "You will spend 3 days per week in the office.", True, "hybrid"),
        # expanded explicit remote confirmations in the description
        ("San Francisco, CA", "This role is remote.", True, "remote"),
        ("Austin, TX", "This position is remote within the US.", True, "remote"),
        ("Denver, CO", "We are a fully distributed team.", True, "remote"),
        ("Chicago, IL", "Work from anywhere in the world.", True, "remote"),
        ("Seattle, WA", "We are a remote-first company.", True, "remote"),
        ("Boston, MA", "This job is 100% remote.", True, "remote"),
        ("New York, NY", "The role is fully remote.", True, "remote"),
    ],
)
def test_classify_work_type_table(location, description, is_remote_hint, expected):
    assert classify_work_type(location, description, is_remote_hint) == expected


def test_reported_remote_flag_skips_heuristic_downgrade():
    """An ATS-reported remote flag is trusted even with a city location."""
    assert classify_work_type(
        "San Francisco, CA", "", True, remote_flag_reported=True,
    ) == "remote"
    # description office-chatter must not downgrade a board-confirmed remote job
    assert classify_work_type(
        "New York, NY",
        "Optional: work from the office whenever you like.",
        True,
        remote_flag_reported=True,
    ) == "remote"
    # without the flag the same inputs stay skeptical
    assert classify_work_type("San Francisco, CA", "", True) == "hybrid"


def test_classify_job_work_type_helper():
    from job_finder.company_classifier import classify_job_work_type

    wt, conf = classify_job_work_type({
        "location": "San Francisco, CA",
        "description": "",
        "is_remote": True,
        "remote_flag_reported": True,
    })
    assert (wt, conf) == ("remote", "reported")

    wt, conf = classify_job_work_type({
        "location": "San Francisco, CA",
        "description": "",
        "is_remote": True,
    })
    assert (wt, conf) == ("hybrid", "inferred")


# ── Scrapers thread the definitive remote flag through the job dict ──────────

def test_ashby_remote_flag_reported(monkeypatch):
    from job_finder.tools.scrapers import ashby

    payload = {
        "jobs": [
            {"title": "Data Engineer", "location": "San Francisco",
             "jobUrl": "u1", "isRemote": True},
            {"title": "Senior Data Engineer", "location": "San Francisco",
             "jobUrl": "u2", "isRemote": False},
        ]
    }
    monkeypatch.setattr(ashby, "_get_json", lambda *a, **k: payload)
    jobs = ashby._fetch_company_jobs("acme", ["data engineer"])
    by_url = {j["url"]: j for j in jobs}
    assert by_url["u1"]["remote_flag_reported"] is True
    assert by_url["u2"]["remote_flag_reported"] is False


def test_ashby_flagged_remote_job_with_city_stays_remote(monkeypatch):
    from job_finder.company_classifier import classify_job_work_type
    from job_finder.tools.scrapers import ashby

    payload = {
        "jobs": [
            {"title": "Data Engineer", "location": "San Francisco",
             "jobUrl": "u1", "isRemote": True},
        ]
    }
    monkeypatch.setattr(ashby, "_get_json", lambda *a, **k: payload)
    job = ashby._fetch_company_jobs("acme", ["data engineer"])[0]
    wt, conf = classify_job_work_type(job)
    assert wt == "remote"
    assert conf == "reported"


def test_lever_workplace_type_remote_is_reported(monkeypatch):
    from job_finder.tools.scrapers import lever

    payload = [
        {"text": "Data Engineer", "categories": {"location": "Austin, TX"},
         "workplaceType": "remote", "hostedUrl": "u1",
         "descriptionPlain": "x"},
        {"text": "Senior Data Engineer", "categories": {"location": "Remote - US"},
         "workplaceType": "hybrid", "hostedUrl": "u2",
         "descriptionPlain": "x"},
    ]
    monkeypatch.setattr(lever, "_get_json", lambda *a, **k: payload)
    jobs = lever._fetch_company_postings("acme", ["data engineer"])
    by_url = {j["url"]: j for j in jobs}
    # workplaceType=remote is a definitive ATS flag
    assert by_url["u1"]["remote_flag_reported"] is True
    # 'remote' appearing only in the location text is NOT a definitive flag
    assert by_url["u2"]["remote_flag_reported"] is False


def test_finalize_stamps_work_type_confidence():
    from job_finder.tools.scrapers._utils import finalize_scraper_jobs

    reported, inferred = finalize_scraper_jobs([
        {"title": "a", "remote_flag_reported": True},
        {"title": "b"},
    ])
    assert reported["work_type_confidence"] == "reported"
    assert inferred["work_type_confidence"] == "inferred"
