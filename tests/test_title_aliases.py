"""The pull and the board read one abbreviation table, so they agree on BI.

Oct 12 2026 audit: "BI Engineering, Manager" (Evercommerce) and "Power BI
Manager" never reached the saved role "Manager, Business Intelligence".
The board side is pinned in test_board_audit_oct12.py; this pins the pull.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

ROLES = ["Manager, Business Intelligence", "Data Engineering Manager"]


@pytest.mark.parametrize("title", ["BI Engineering, Manager", "Power BI Manager", "Senior BI Manager"])
@pytest.mark.parametrize("is_remote", [True, False])
def test_pull_keeps_bi_titles_for_a_business_intelligence_role(title, is_remote) -> None:
    from job_finder.tools.scrapers._utils import job_passes_role_filter

    assert job_passes_role_filter({"title": title, "is_remote": is_remote}, ROLES)


@pytest.mark.parametrize("title", ["BIM Manager", "Bilingual Manager"])
def test_pull_does_not_read_bim_or_bilingual_as_bi(title) -> None:
    from job_finder.tools.scrapers._utils import job_passes_role_filter

    assert not job_passes_role_filter({"title": title, "is_remote": True}, ROLES)


def test_a_saved_bi_role_matches_spelled_out_titles() -> None:
    from job_finder.tools.scrapers._utils import _match_roles

    assert _match_roles("Business Intelligence Manager", ["BI Manager"])


def test_board_lane_check_agrees_with_the_pull() -> None:
    from app.services.local_agent_service import _title_is_in_lane

    assert _title_is_in_lane("Power BI Manager", ROLES)
    assert not _title_is_in_lane("BIM Manager", ROLES)
