"""FIX 2: keyword aliasing (ML <-> Machine Learning), word-boundary matching
for short forms, comp-signal hygiene, and certification handling.
"""
from __future__ import annotations

import pytest

from job_finder.scoring.core import score_job_basic
from job_finder.scoring.helpers import keyword_matches

# ── alias expansion + word-boundary matching ──────────────────────────────

ALIAS_CASES = [
    # (jd_text, configured_keyword, should_match)
    ("We build Machine Learning models in production.", "ML", True),
    ("Hands-on ML experience required.", "Machine Learning", True),
    ("Experience with Artificial Intelligence systems.", "AI", True),
    ("Modern JavaScript stack.", "JS", True),
    ("JS-heavy frontend.", "JavaScript", True),
    ("We write TypeScript everywhere.", "TS", True),
    ("Deploy services to Kubernetes clusters.", "K8s", True),
    ("Workloads run on Google Cloud.", "GCP", True),
    ("Amazon Web Services infrastructure.", "AWS", True),
    ("Seeking a Registered Nurse for the ICU.", "RN", True),
    ("Nurse Practitioner license preferred.", "NP", True),
    ("Partner with the Product Manager daily.", "PM", True),
    ("PostgreSQL is our main database.", "postgres", True),
    ("Frontend is built in React.", "react.js", True),
    ("Backend services in Node.js.", "node", True),
    # word-boundary guards: short forms must not match inside other words
    ("Strong HTML and CSS skills.", "ML", False),
    ("Comfortable turning around projects.", "RN", False),
    ("Evening 6pm shift available.", "PM", False),
    ("Painting murals on weekends.", "AI", False),
]


@pytest.mark.parametrize("text,keyword,expected", ALIAS_CASES)
def test_alias_and_boundary_matching(text: str, keyword: str, expected: bool):
    matched = keyword_matches(text, [keyword])
    assert (keyword in matched) is expected


def test_longer_terms_keep_substring_behavior():
    # >3 chars keeps the historical substring match (no boundary requirement)
    assert keyword_matches("We use node.js services.", ["node.js"]) == ["node.js"]
    assert keyword_matches("microservices everywhere", ["services"]) == ["services"]


def test_ml_alias_scores_technical_like_full_form():
    jd = "We need Machine Learning experience for this role."
    resume = "Built machine learning systems at scale."
    short = score_job_basic(jd, resume, config={"keywords": {"technical": ["ML"]}})
    full = score_job_basic(
        jd, resume, config={"keywords": {"technical": ["Machine Learning"]}},
    )
    assert short["technical_score"] == pytest.approx(full["technical_score"])


# ── comp signal hygiene ───────────────────────────────────────────────────

def test_default_comp_signals_ignore_company_name_in_location():
    """'Apple Valley, MN' must not raise comp_potential via the default signals."""
    apple = score_job_basic(
        "Clinic receptionist needed in Apple Valley, MN.", "resume text", config={},
    )
    plain = score_job_basic(
        "Clinic receptionist needed in Springfield, IL.", "resume text", config={},
    )
    assert apple["comp_potential_score"] == pytest.approx(
        plain["comp_potential_score"]
    )


def test_configured_comp_terms_only_no_location_inflation():
    cfg = {
        "keywords": {
            "high_comp_signals": ["equity", "rsu", "signing bonus", "stock options"],
        }
    }
    apple = score_job_basic(
        "Clinic receptionist needed in Apple Valley, MN.", "resume text", config=cfg,
    )
    plain = score_job_basic(
        "Clinic receptionist needed in Springfield, IL.", "resume text", config=cfg,
    )
    assert apple["comp_potential_score"] == pytest.approx(
        plain["comp_potential_score"]
    )


# ── certifications ────────────────────────────────────────────────────────

_CERT_JD = (
    "The AWS Certified Solutions Architect certification is required for this role. "
    "You will design cloud architecture."
)


def test_matching_cert_boosts_technical_and_avoids_gap():
    base_cfg = {"keywords": {"technical": ["python"]}}
    cert_cfg = {
        "keywords": {"technical": ["python"]},
        "certifications": ["AWS Certified Solutions Architect"],
    }
    resume = "Cloud engineer, AWS Certified Solutions Architect."
    with_cert = score_job_basic(_CERT_JD, resume, config=cert_cfg)
    without_cert = score_job_basic(_CERT_JD, resume, config=base_cfg)

    assert with_cert["technical_score"] > without_cert["technical_score"]
    assert not any("certification" in g.lower() for g in with_cert["key_gaps"])


def test_missing_required_cert_appends_gap_note():
    result = score_job_basic(
        _CERT_JD, "Generalist resume.", config={"keywords": {"technical": ["python"]}},
    )
    assert any("certification" in g.lower() for g in result["key_gaps"])


def test_no_cert_gap_when_jd_does_not_require_one():
    result = score_job_basic(
        "Build data pipelines with Python.", "Python engineer.",
        config={"keywords": {"technical": ["python"]}},
    )
    assert not any("certification" in g.lower() for g in result["key_gaps"])
