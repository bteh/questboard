"""Pay filters annualize per-period rates at comparison time.

Most stored rows carry only the raw per-period numbers (an hourly $50, a
daily $400) with the annualized columns empty, so an annual-scale floor
used to silently delete them: 50 < 60000. The filter now compares
coalesce(annualized, raw * period multiplier): hourly*2080, daily*260,
weekly*52, monthly*12, anything else as-is. Per-gig "session" pay is not a
rate at all, so those rows are treated like no-stated-pay: always kept,
never compared.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "job_tracker.db"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("WORKSPACE_STORAGE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.setenv("HOSTED_MODE", "false")
    monkeypatch.setenv("MANAGE_SCHEMA_ON_STARTUP", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    for module_name in list(sys.modules):
        if (
            module_name == "app"
            or module_name.startswith("app.")
            or module_name == "job_finder.models"
            or module_name.startswith("job_finder.models.")
        ):
            sys.modules.pop(module_name, None)

    backend_db = importlib.import_module("app.models.database")
    backend_db.init_db(str(db_path))
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(db_path))
    app_main = importlib.import_module("app.main")

    with TestClient(app_main.app) as client:
        yield client, jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def _seed(jf_db) -> None:
    """Old-style rows: raw per-period numbers, annualized columns empty."""
    rows = (
        # $50/hr = $104,000 a year
        ("Hourly fifty", "https://example.com/pay/hourly", 50.0, 50.0, "hourly"),
        # per-gig pay, not a rate: never compared to an annual scale
        ("Session two hundred", "https://example.com/pay/session", 200.0, 200.0, "session"),
        # a real annual figure stays exactly as before
        ("Annual one-ninety", "https://example.com/pay/annual", 190000.0, 190000.0, "yearly"),
        # $400/day = $104,000; $2,000/week = $104,000; $10,000/month = $120,000
        ("Daily four hundred", "https://example.com/pay/daily", 400.0, 400.0, "daily"),
        ("Weekly two thousand", "https://example.com/pay/weekly", 2000.0, 2000.0, "weekly"),
        ("Monthly ten thousand", "https://example.com/pay/monthly", 10000.0, 10000.0, "monthly"),
    )
    for title, url, lo, hi, period in rows:
        jf_db.save_application(
            job_title=title,
            company="Acme",
            job_url=url,
            salary_min=lo,
            salary_max=hi,
            salary_period=period,
        )


def _titles(payload: dict) -> set[str]:
    return {item["job_title"] for item in payload["items"]}


def test_hourly_rate_clears_an_annual_floor(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # $50/hr annualizes to $104k, well above a $60k floor. Before the fix
    # the raw 50 was compared to 60000 and the row silently vanished.
    resp = client.get("/api/v1/applications", params={"salary_min": 60000})
    assert resp.status_code == 200, resp.text
    assert "Hourly fifty" in _titles(resp.json())


def test_session_pay_survives_an_annual_floor(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # A $200 gig is not a $200 salary; it can neither pass nor fail an
    # annual scale, so it stays, like a row with no stated pay.
    resp = client.get("/api/v1/applications", params={"salary_min": 150000})
    assert "Session two hundred" in _titles(resp.json())


def test_session_pay_survives_an_annual_ceiling(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    resp = client.get("/api/v1/applications", params={"salary_max": 100})
    assert "Session two hundred" in _titles(resp.json())


def test_annual_rows_filter_exactly_as_before(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    kept = client.get("/api/v1/applications", params={"salary_min": 150000})
    assert "Annual one-ninety" in _titles(kept.json())

    dropped = client.get("/api/v1/applications", params={"salary_min": 200000})
    assert "Annual one-ninety" not in _titles(dropped.json())


def test_daily_weekly_monthly_rates_annualize(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # daily 400*260 = 104k, weekly 2000*52 = 104k, monthly 10000*12 = 120k
    kept = _titles(client.get("/api/v1/applications", params={"salary_min": 100000}).json())
    assert {"Daily four hundred", "Weekly two thousand", "Monthly ten thousand"} <= kept

    dropped = _titles(client.get("/api/v1/applications", params={"salary_min": 125000}).json())
    assert "Daily four hundred" not in dropped
    assert "Weekly two thousand" not in dropped
    assert "Monthly ten thousand" not in dropped


def test_hourly_rate_respects_the_ceiling_at_annual_scale(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)

    # $104k a year sits above a $100k ceiling and under a $110k one.
    over = client.get("/api/v1/applications", params={"salary_max": 100000})
    assert "Hourly fifty" not in _titles(over.json())

    under = client.get("/api/v1/applications", params={"salary_max": 110000})
    assert "Hourly fifty" in _titles(under.json())


def test_annualized_columns_still_win_over_the_raw_numbers(api_client) -> None:
    client, jf_db = api_client
    _seed(jf_db)
    # a row where the parser already annualized: coalesce must prefer it
    jf_db.save_application(
        job_title="Pre-annualized hourly",
        company="Acme",
        job_url="https://example.com/pay/pre-annualized",
        salary_min=5.0,
        salary_max=5.0,
        salary_period="hourly",
        salary_min_annualized=150000.0,
        salary_max_annualized=150000.0,
    )

    resp = client.get("/api/v1/applications", params={"salary_min": 140000})
    assert "Pre-annualized hourly" in _titles(resp.json())
