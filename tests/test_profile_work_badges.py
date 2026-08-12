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


def test_my_roles_total_and_pages_are_not_capped_at_300(work_db) -> None:
    """A full database lane must not be disguised as a 300-job lane."""
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add_all([
        ApplicationRecord(
            job_title=f"Data Engineering Manager {index}",
            company=f"Overflow Company {index}",
            job_url=f"https://overflow.example/jobs/{index}",
            source="Greenhouse",
            vertical="career",
            location="Remote, United States",
            remote_scope="us",
            is_remote=True,
            work_type="remote",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now - timedelta(seconds=index),
        )
        for index in range(320)
    ])
    work_db.commit()

    first = _list_profile_work(work_db, page=1, page_size=24)
    tail = _list_profile_work(work_db, page=14, page_size=24)

    assert first.total == 322
    assert first.reviewed_count + first.unreviewed_count == first.total
    assert len(tail.items) == 10


def test_staffing_preference_applies_to_my_roles_and_source_shelves(work_db) -> None:
    from app.models.workspace import WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add(
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company="Jobgether",
            job_url="https://jobs.lever.co/jobgether/data-manager",
            source="Lever",
            vertical="career",
            location="Remote, United States",
            remote_scope="us",
            is_remote=True,
            work_type="remote",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        )
    )
    work_db.commit()

    assert "Jobgether" not in {
        item.company for item in _list_profile_work(work_db).items
    }
    assert "Jobgether" not in {
        item.company for item in _list_profile_work(work_db, source_category="ats").items
    }

    prefs = work_db.query(WorkspacePreferences).filter_by(workspace_id="configured").one()
    prefs.exclude_staffing_agencies = False
    work_db.commit()
    assert "Jobgether" in {
        item.company for item in _list_profile_work(work_db).items
    }


def test_my_roles_view_filters_can_only_narrow_saved_eligibility(work_db) -> None:
    """Toolbar values must never weaken the search used to pull and rank.

    This guards the three replacement bugs that mattered most in practice: a
    lower visible pay floor used to replace the saved floor, a longer visible
    date window resurrected stale rows, and a different city replaced the
    saved location instead of intersecting it.
    """
    from app.models.workspace import WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    prefs = work_db.query(WorkspacePreferences).filter_by(
        workspace_id="configured"
    ).one()
    prefs.min_base = 190000
    prefs.compensation_currency = "USD"
    prefs.max_days_old = 14
    prefs.preferred_places_json = json.dumps(
        [
            {
                "label": "Los Angeles, CA",
                "kind": "city",
                "match_scope": "city",
                "city": "Los Angeles",
                "region": "California",
                "country": "United States",
                "country_code": "US",
            }
        ]
    )
    work_db.add_all(
        [
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Below Saved Floor Co",
                job_url="https://filters.example/jobs/low-pay",
                source="Greenhouse",
                vertical="career",
                location="Remote, United States",
                remote_scope="us",
                is_remote=True,
                salary_min=120000,
                salary_max=120000,
                salary_currency="USD",
                salary_period="annual",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Older Than Saved Window Co",
                job_url="https://filters.example/jobs/old",
                source="Greenhouse",
                vertical="career",
                location="Remote, United States",
                remote_scope="us",
                is_remote=True,
                date_posted=(now - timedelta(days=20)).isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
        ]
    )
    work_db.commit()

    baseline = _list_profile_work(work_db)
    baseline_companies = {item.company for item in baseline.items}
    assert "Live Co" in baseline_companies
    assert "Below Saved Floor Co" not in baseline_companies
    assert "Older Than Saved Window Co" not in baseline_companies
    assert "Paying Co" not in baseline_companies  # New York, on-site

    weaker_floor = _list_profile_work(work_db, salary_min=100000)
    longer_window = _list_profile_work(work_db, posted_within_days=30)
    other_city = _list_profile_work(
        work_db,
        location="New York",
        location_strict=True,
    )
    for narrowed in (weaker_floor, longer_window, other_city):
        assert {item.company for item in narrowed.items} <= baseline_companies
        assert narrowed.total <= baseline.total

    assert "Below Saved Floor Co" not in {
        item.company for item in weaker_floor.items
    }
    assert "Older Than Saved Window Co" not in {
        item.company for item in longer_window.items
    }
    assert "Paying Co" not in {item.company for item in other_city.items}


def test_source_shelf_browses_inventory_beyond_saved_role_constraints(work_db) -> None:
    """Source chips remain discovery shelves, while their own filters bite."""
    from app.models.workspace import WorkspacePreferences
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    prefs = work_db.query(WorkspacePreferences).filter_by(
        workspace_id="configured"
    ).one()
    prefs.min_base = 190000
    prefs.compensation_currency = "USD"
    work_db.add(
        ApplicationRecord(
            job_title="Data Engineering Manager",
            company="Shelf Discovery Co",
            job_url="https://filters.example/jobs/shelf",
            source="Greenhouse",
            vertical="career",
            location="Remote, United States",
            remote_scope="us",
            is_remote=True,
            salary_min=120000,
            salary_max=120000,
            salary_currency="USD",
            salary_period="annual",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        )
    )
    work_db.commit()

    assert "Shelf Discovery Co" not in {
        item.company for item in _list_profile_work(work_db).items
    }
    shelf = _list_profile_work(work_db, source_category="ats")
    assert "Shelf Discovery Co" in {item.company for item in shelf.items}
    filtered_shelf = _list_profile_work(
        work_db,
        source_category="ats",
        salary_min=190000,
        salary_currency="USD",
    )
    assert "Shelf Discovery Co" not in {
        item.company for item in filtered_shelf.items
    }


def test_crypto_shelf_uses_industry_identity_across_sources(work_db) -> None:
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add_all(
        [
            ApplicationRecord(
                job_title="Staff Platform Engineer",
                company="Helius",
                job_url="https://jobs.ashbyhq.com/helius/platform",
                source="Ashby",
                industry_tags='["crypto"]',
                ecosystem_tags='["solana"]',
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            # Legacy crypto-source row: the source fallback keeps it visible
            # until startup taxonomy backfill runs.
            ApplicationRecord(
                job_title="Senior Data Engineer",
                company="Portfolio Crypto Co",
                job_url="https://portfolio.example/crypto-data",
                source="Getro",
                industry_tags="[]",
                ecosystem_tags="[]",
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
        ]
    )
    work_db.commit()

    response = _list_profile_work(work_db, source_category="crypto")
    assert {item.company for item in response.items} == {
        "Helius",
        "Portfolio Crypto Co",
    }
    assert response.source_categories["crypto"] == response.total == 2
    helius = next(item for item in response.items if item.company == "Helius")
    assert helius.industry_tags == ["crypto"]
    assert helius.ecosystem_tags == ["solana"]


def test_startup_shelf_uses_strict_company_or_founding_identity_across_sources(
    work_db,
) -> None:
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add_all(
        [
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Verified Seed Co",
                job_url="https://jobs.ashbyhq.com/seed/data",
                source="Ashby",
                company_type="Early Startup",
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Founding Data Engineer",
                company="Founding Seat Co",
                job_url="https://builtin.example/founding-data",
                source="BuiltIn",
                company_type="Unknown",
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="YC Source Co",
                job_url="https://workatastartup.com/jobs/123",
                source="workatastartup",
                company_type="Unknown",
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            # Broad boards and unknown company stage are not proof of startup.
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Ordinary Broad Board Co",
                job_url="https://builtin.example/ordinary-data",
                source="BuiltIn",
                company_type="Unknown",
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Founding Data Engineer",
                company="Expired Founding Co",
                job_url="https://builtin.example/expired-founding",
                source="BuiltIn",
                company_type="Unknown",
                url_status="dead",
                vertical="career",
                location="Remote, United States",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
        ]
    )
    work_db.commit()

    response = _list_profile_work(work_db, source_category="startup")
    assert {item.company for item in response.items} == {
        "Verified Seed Co",
        "Founding Seat Co",
        "YC Source Co",
    }
    assert response.source_categories["startup"] == response.total == 3

    founding = _list_profile_work(
        work_db,
        source_category="startup",
        founding_only=True,
    )
    assert [item.company for item in founding.items] == ["Founding Seat Co"]
    assert founding.source_categories["startup"] == founding.total == 1


def test_roles_view_honors_the_pay_ceiling(work_db) -> None:
    everything = _list_profile_work(work_db)
    assert "Paying Co" in [item.company for item in everything.items]

    capped = _list_profile_work(work_db, salary_max=250000)
    companies = [item.company for item in capped.items]
    assert "Paying Co" not in companies
    assert capped.total == len(companies)


def test_founding_filter_keeps_named_first_hire_and_explicit_team_roles(work_db) -> None:
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add_all(
        [
            ApplicationRecord(
                job_title="Founding Data Engineering Manager",
                company="Named Founding Co",
                job_url="https://founding.example/jobs/named",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="First Hire Co",
                job_url="https://founding.example/jobs/first-hire",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="You will be our first dedicated data hire.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Founding Team Seat Co",
                job_url="https://founding.example/jobs/team-seat",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="Join our founding team and build the data function.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Ordinary Co",
                job_url="https://founding.example/jobs/ordinary",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="Join an established data platform group.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Founder Bio Co",
                job_url="https://founding.example/jobs/founder-bio",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="Our founding team previously built products at Acme.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
        ]
    )
    work_db.commit()

    response = _list_profile_work(
        work_db,
        source_category="ats",
        founding_only=True,
    )
    assert {item.company for item in response.items} == {
        "Named Founding Co",
        "First Hire Co",
        "Founding Team Seat Co",
    }
    assert response.source_categories["ats"] == 3


def test_founding_filter_honors_the_default_my_roles_lane(work_db) -> None:
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add_all(
        [
            ApplicationRecord(
                job_title="Founding Data Engineering Manager",
                company="Founding Lane Co",
                job_url="https://founding.example/jobs/lane",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="Build the data function from scratch.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
            ApplicationRecord(
                job_title="Data Engineering Manager",
                company="Ordinary Lane Co",
                job_url="https://founding.example/jobs/ordinary-lane",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="Lead an established data engineering team.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            ),
        ]
    )
    work_db.commit()

    response = _list_profile_work(work_db, founding_only=True)
    assert [item.company for item in response.items] == ["Founding Lane Co"]
    assert response.total == 1


def test_founding_filter_runs_before_the_bounded_role_shortlist(work_db) -> None:
    """A founding result must not be crowded out by 300 ordinary role rows."""
    from job_finder.models.database import ApplicationRecord

    now = datetime.now(timezone.utc)
    work_db.add(
        ApplicationRecord(
            job_title="Founding Data Engineering Manager",
            company="Founding Needle Co",
            job_url="https://founding.example/jobs/needle",
            source="Greenhouse",
            vertical="career",
            location="Los Angeles, CA",
            description="Be the first data hire and build the platform.",
            date_posted=now.isoformat(),
            date_confidence="exact",
            date_found=now,
        )
    )
    work_db.add_all(
        [
            ApplicationRecord(
                job_title="Staff Data Engineer",
                company=f"Ordinary Exact Match {index:03d}",
                job_url=f"https://ordinary.example/jobs/{index}",
                source="Greenhouse",
                vertical="career",
                location="Los Angeles, CA",
                description="Join an established data platform team.",
                date_posted=now.isoformat(),
                date_confidence="exact",
                date_found=now,
            )
            for index in range(310)
        ]
    )
    work_db.commit()

    response = _list_profile_work(work_db, founding_only=True)
    assert [item.company for item in response.items] == ["Founding Needle Co"]
    assert response.total == 1


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
