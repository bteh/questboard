"""The "Startups & founding" chip must count the classifier's real tiers.

Bug: the chip's taxonomy leg checked company_type == "early startup", a
string the classifier never emits (its vocabulary is "Early Startup",
"Elite Startup", "Growth Stage", ...). Brian's board showed 23 rows tagged
Elite Startup and the chip said 2.

Growth Stage counts only when funding-verified: the classifier also stamps
"Growth Stage" as the default for any unknown company arriving via a
Greenhouse/Lever/Ashby board, and the chip promises that board membership
alone never makes a startup.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
def db_session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOSTED_MODE", "false")
    import importlib

    database = importlib.import_module("job_finder.models.database")
    database.init_db(str(tmp_path / "job_tracker.db"))
    session = database._SessionLocal()
    yield session
    session.close()
    database._SessionLocal.remove()


def _row(database, **kwargs):
    defaults = dict(job_title="Data Engineer", location="Remote, US", source="greenhouse")
    defaults.update(kwargs)
    return database.ApplicationRecord(**defaults)


def test_startup_chip_counts_classifier_tiers(db_session):
    import importlib

    database = importlib.import_module("job_finder.models.database")
    from app.services import application_service

    rows = {
        "elite": _row(database, company="Scale-ish", job_url="https://x/elite", company_type="Elite Startup"),
        "early": _row(database, company="TinyCo", job_url="https://x/early", company_type="Early Startup"),
        "growth_verified": _row(
            database,
            company="SeriesBCo",
            job_url="https://x/growthv",
            company_type="Growth Stage",
            funding_stage="Series B",
        ),
        "growth_default": _row(
            database, company="BoardDefaultCo", job_url="https://x/growthd", company_type="Growth Stage"
        ),
        "bigtech": _row(database, company="Netflix", job_url="https://x/big", company_type="Big Tech"),
        "unknown": _row(database, company="MysteryCo", job_url="https://x/unk", company_type="Unknown"),
        "yc_source": _row(
            database, company="Hive", job_url="https://x/yc", source="workatastartup", company_type="Unknown"
        ),
    }
    db_session.add_all(rows.values())
    db_session.commit()

    matched = {
        r.company
        for r in db_session.query(database.ApplicationRecord)
        .filter(application_service.source_category_condition(database.ApplicationRecord, "startup"))
        .all()
    }

    assert rows["elite"].company in matched, "Elite Startup tier must count as a startup"
    assert rows["early"].company in matched, "Early Startup tier must count as a startup"
    assert rows["growth_verified"].company in matched, "funding-verified Growth Stage must count"
    assert rows["yc_source"].company in matched, "startup-board source must still count"
    assert rows["growth_default"].company not in matched, (
        "unverified Growth Stage is the ats-board default; board membership alone must not count"
    )
    assert rows["bigtech"].company not in matched
    assert rows["unknown"].company not in matched
