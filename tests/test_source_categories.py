"""Source categories keep the promise their chip makes.

Clicked "Startup & founder", got Netflix. BuiltIn was registered as a startup
board and it is not one: it is a general tech-hub board carrying Netflix,
Disney, and GitLab. That mislabel also leaked into company classification,
where a startup-category source is a fallback signal for the Early Startup
tier, so a Netflix row with no funding data could read as an early startup
because of which board it arrived on.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.company_classifier import classify_company  # noqa: E402
from job_finder.tools.scrapers import get_registry  # noqa: E402


def test_builtin_is_not_a_startup_board():
    """The Netflix case: BuiltIn lists enterprises, so the Startup & founder
    chip must not include it."""
    assert get_registry()["builtin"].category == "general"


def test_workatastartup_keeps_the_startup_promise():
    """YC's board is the one source there that is genuinely startup-only."""
    assert get_registry()["workatastartup"].category == "startup"


def test_getro_community_is_labeled_as_a_vc_portfolio_not_early_startup():
    assert get_registry()["getro_startups"].category == "vc"


def test_a_builtin_company_is_not_presumed_an_early_startup():
    """Netflix via BuiltIn, no funding signals: the source must not tier it."""
    assert classify_company("Netflix", source_category="general") != "Early Startup"


def test_a_workatastartup_company_still_tiers_as_early_startup():
    assert classify_company("SomeTinyCo", source_category="startup") == "Early Startup"
