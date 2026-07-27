"""The work lane's source-category chips agree with the results.

The badges used to count the FULL career inventory, ignoring the board's
place / pay / search filters and dead links, while the rows below honored
them; and the category browse view included dead links "My roles" hides.
Badges now run through the same filtered query as the results, category
browse excludes dead links, and both views take the server-side pay
ceiling (salary_max).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _path in (BACKEND_PATH, SRC_PATH):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


@pytest.fixture()
def work_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")

    from app.models.database import get_db, init_db
    from app.models.workspace import Workspace, WorkspacePreferences, WorkspaceResume
    from job_finder.models.database import ApplicationRecord

    init_db(str(db_path))
    generator = get_db()
    db = next(generator)
    now = datetime.now(timezone.utc)

    db.add(
        Workspace(
            id="configured",
            name="Configured",
            slug="configured",
            last_active_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    db.add(
        WorkspacePreferences(
            workspace_id="configured",
            roles_json=json.dumps(["Data Engineering Manager"]),
            keywords_json=json.dumps(["data platform"]),
            workplace_preference="remote_friendly",
            max_days_old=14,
            current_level="manager",
        )
    )
    db.add(
        WorkspaceResume(
            workspace_id="configured",
            original_filename="resume.pdf",
            parse_status="parsed",
            file_sha256="a" * 64,
            extracted_text="Data engineering leader.",
            updated_at=now,
        )
    )

    def career(title, company, url, source, **kw):
        return ApplicationRecord(
            job_title=title,
            company=company,
            job_url=url,
            source=source,
            vertical="career",
            remote_scope="us",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
            **kw,
        )

    db.add_all(
        [
            # ats (greenhouse): one live LA row, one DEAD row
            career(
                "Data Engineering Manager", "Live Co",
                "https://live.example/jobs/data", "Greenhouse",
                location="Los Angeles, CA", state_codes=",CA,",
                description="Own the data platform. Snowflake heavy.",
            ),
            career(
                "Data Engineering Manager", "Ghost Co",
                "https://ghost.example/jobs/data", "Greenhouse",
                location="Los Angeles, CA", state_codes=",CA,",
                url_status="dead",
            ),
            # remote (himalayas): a New York row with stated annual pay
            career(
                "Data Engineering Manager", "Paying Co",
                "https://pay.example/jobs/data", "Himalayas",
                location="New York, NY", state_codes=",NY,",
                salary_min=300000.0, salary_max=340000.0,
                salary_min_annualized=300000.0, salary_max_annualized=340000.0,
            ),
        ]
    )
    db.commit()
    yield db
    db.close()
    try:
        next(generator)
    except StopIteration:
        pass


def _list_profile_work(db, **overrides):
    from app.api.applications import list_profile_work

    kwargs = dict(
        search=None,
        location=None,
        location_strict=False,
        salary_min=None,
        salary_max=None,
        is_remote=None,
        posted_within_days=None,
        source_category=None,
        page=1,
        page_size=24,
        workspace=SimpleNamespace(workspace=SimpleNamespace(id="configured")),
        db=db,
    )
    kwargs.update(overrides)
    return list_profile_work(**kwargs)


def test_badges_exclude_dead_links_like_the_results_do(work_db) -> None:
    response = _list_profile_work(work_db)
    # 2 Greenhouse rows exist but one is a confirmed-dead link
    assert response.source_categories.get("ats") == 1
    assert response.source_categories.get("remote") == 1


def test_badges_honor_the_place_filter(work_db) -> None:
    response = _list_profile_work(work_db, location="Los Angeles", location_strict=True)
    assert response.source_categories.get("ats") == 1
    # the New York row is not reachable from LA under near-me-only
    assert "remote" not in response.source_categories


def test_badges_honor_the_pay_filters(work_db) -> None:
    floor = _list_profile_work(work_db, salary_min=250000)
    # only the 300-340k row states pay above the floor; no-pay rows keep
    assert floor.source_categories.get("remote") == 1
    assert floor.source_categories.get("ats") == 1  # no stated pay: kept

    ceiling = _list_profile_work(work_db, salary_max=250000)
    assert "remote" not in ceiling.source_categories
    assert ceiling.source_categories.get("ats") == 1


def test_badges_honor_the_search_box(work_db) -> None:
    response = _list_profile_work(work_db, search="Snowflake")
    assert response.source_categories.get("ats") == 1
    assert "remote" not in response.source_categories


def test_category_browse_excludes_dead_links(work_db) -> None:
    response = _list_profile_work(work_db, source_category="ats")
    companies = [item.company for item in response.items]
    assert "Live Co" in companies
    assert "Ghost Co" not in companies
    assert response.total == 1


def test_category_browse_honors_the_pay_ceiling(work_db) -> None:
    response = _list_profile_work(work_db, source_category="remote", salary_max=250000)
    assert response.total == 0


def test_roles_view_honors_the_pay_ceiling(work_db) -> None:
    everything = _list_profile_work(work_db)
    assert "Paying Co" in [item.company for item in everything.items]

    capped = _list_profile_work(work_db, salary_max=250000)
    companies = [item.company for item in capped.items]
    assert "Paying Co" not in companies
    assert capped.total == len(companies)


# ── a chip must never promise more rows than clicking it delivers ────────────

@pytest.fixture()
def crowded_work_db(work_db):
    """One category holding more rows than the browse query used to fetch.

    Real board, 2026-07-27: the Remote chip read 632 while clicking it showed
    400, because the count query was uncapped and the browse query asked for
    page_size=400. 232 rows were unreachable from the UI.
    """
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add_all([
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company=f"Remote Co {i:04d}",
            job_url=f"https://remote.example/jobs/{i}",
            source="Himalayas",
            vertical="career",
            remote_scope="us",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now - timedelta(minutes=i),
        )
        for i in range(450)
    ])
    work_db.commit()
    return work_db


def test_chip_count_matches_the_rows_clicking_it_returns(crowded_work_db) -> None:
    response = _list_profile_work(crowded_work_db, source_category="remote")
    assert response.total == response.source_categories["remote"], (
        f"the Remote chip promises {response.source_categories['remote']} rows "
        f"but clicking it returns {response.total}"
    )


def test_every_chip_agrees_with_its_own_browse_view(crowded_work_db) -> None:
    """The invariant, for each category, not just the crowded one."""
    counts = _list_profile_work(crowded_work_db).source_categories
    for category, promised in counts.items():
        delivered = _list_profile_work(crowded_work_db, source_category=category).total
        assert delivered == promised, (
            f"{category}: chip says {promised}, browse returns {delivered}"
        )
