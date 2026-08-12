from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from job_finder import company_taxonomy
from job_finder.models import maintenance


def _redirect_catalog(monkeypatch, tmp_path):
    monkeypatch.setattr(company_taxonomy, "_CACHE_PATH", tmp_path / "company_catalog.json")
    monkeypatch.setattr(company_taxonomy, "_CATALOG_CACHE", None)
    monkeypatch.setattr(company_taxonomy, "_CATALOG_CACHE_PATH", "")
    monkeypatch.setattr(company_taxonomy, "_CATALOG_CACHE_MTIME_NS", -1)
    # test_ats_discovery intentionally reloads this module; resolve the current
    # object so full-suite order cannot leave this test patching a stale module.
    ats_discovery = importlib.import_module("job_finder.tools.scrapers._ats_discovery")
    monkeypatch.setattr(ats_discovery, "_CACHE_DIR", tmp_path / "ats-cache")
    return ats_discovery


def test_crypto_source_teaches_company_identity_and_promotes_ats(monkeypatch, tmp_path) -> None:
    ats_discovery = _redirect_catalog(monkeypatch, tmp_path)
    job = {
        "title": "Staff Platform Engineer, Observability",
        "company": "New Solana Portfolio Co",
        "source": "getro",
        "url": "https://jobs.ashbyhq.com/new-solana-portfolio/abc-123",
        "description": "Build reliable infrastructure.",
        "company_crypto": True,
    }

    changed = company_taxonomy.observe_jobs([job], source_category="crypto")

    assert changed == 1
    assert job["industry_tags"] == ["crypto"]
    assert job["crypto"] is True
    assert company_taxonomy.is_known_crypto_company("New Solana Portfolio Co")
    slugs, _ = ats_discovery.load_cached_slugs("ashby")
    assert "new-solana-portfolio" in slugs

    industries, ecosystems = company_taxonomy.classify_job_taxonomy(
        company="New Solana Portfolio Co",
        source="ashby",
        title="Staff Platform Engineer, Observability",
    )
    assert industries == ["crypto"]
    assert ecosystems == []


def test_aggregator_direct_apply_url_promotes_missing_ashby_board(
    monkeypatch, tmp_path,
) -> None:
    ats_discovery = _redirect_catalog(monkeypatch, tmp_path)
    job = {
        "title": "Sr. Manager, Data Engineering & Analytics",
        "company": "Serve Robotics",
        "source": "builtin",
        "url": "https://builtin.com/job/sr-manager-data-engineering-analytics/9414145",
        "direct_application_url": (
            "https://jobs.ashbyhq.com/serverobotics/"
            "887ef3a7-3bde-4649-820a-a54b0afc4cf9"
        ),
        "description": "Lead the data engineering and analytics team.",
    }

    company_taxonomy.observe_jobs([job], source_category="general")

    slugs, _ = ats_discovery.load_cached_slugs("ashby")
    assert "serverobotics" in slugs


def test_crypto_listing_does_not_reclassify_every_job_at_general_employer(
    monkeypatch, tmp_path,
) -> None:
    _redirect_catalog(monkeypatch, tmp_path)
    crypto_job = {
        "title": "Blockchain Data Engineer",
        "company": "General Cloud Corp",
        "source": "cryptojobslist",
        "description": "Build digital asset pipelines.",
    }
    company_taxonomy.observe_jobs([crypto_job], source_category="crypto")
    assert crypto_job["industry_tags"] == ["crypto"]
    assert not company_taxonomy.is_known_crypto_company("General Cloud Corp")

    ordinary, _ = company_taxonomy.classify_job_taxonomy(
        company="General Cloud Corp",
        source="linkedin",
        title="Data Engineering Manager",
        description="Build a general cloud analytics platform.",
    )
    assert ordinary == []


def test_ecosystem_tags_make_a_generic_source_job_crypto(monkeypatch, tmp_path) -> None:
    _redirect_catalog(monkeypatch, tmp_path)
    industries, ecosystems = company_taxonomy.classify_job_taxonomy(
        company="New Protocol Co",
        source="greenhouse",
        title="Senior Data Engineer, Solana Ecosystem",
        description="Own streaming pipelines.",
    )
    assert industries == ["crypto"]
    assert ecosystems == ["solana"]


def test_generic_prose_requires_more_than_one_weak_mention(monkeypatch, tmp_path) -> None:
    _redirect_catalog(monkeypatch, tmp_path)
    one, _ = company_taxonomy.classify_job_taxonomy(
        company="Ordinary Fintech",
        source="linkedin",
        title="Data Engineer",
        description="Some customers pay with crypto.",
    )
    two, _ = company_taxonomy.classify_job_taxonomy(
        company="Digital Asset Infra",
        source="linkedin",
        title="Data Engineer",
        description="Build blockchain analytics for digital asset markets.",
    )
    assert one == []
    assert two == ["crypto"]


def test_ambiguous_optimism_word_is_not_an_ecosystem(monkeypatch, tmp_path) -> None:
    _redirect_catalog(monkeypatch, tmp_path)
    industries, ecosystems = company_taxonomy.classify_job_taxonomy(
        company="Equipment Company",
        source="greenhouse",
        title="Analytics Engineer",
        description="We have optimism about the future of construction.",
    )
    assert industries == []
    assert ecosystems == []


def test_taxonomy_repair_removes_poisoned_company_tags(monkeypatch, tmp_path) -> None:
    _redirect_catalog(monkeypatch, tmp_path)
    engine = create_engine(f"sqlite:///{tmp_path / 'taxonomy.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            "id INTEGER PRIMARY KEY, company TEXT, source TEXT, job_title TEXT, "
            "description TEXT, industry_tags TEXT, ecosystem_tags TEXT, vertical TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO applications VALUES "
            "(1, 'Microsoft', 'builtin', 'Data Science Manager', "
            "'Build ordinary cloud systems', '[\"crypto\"]', '[]', 'career'), "
            "(2, 'Microsoft', 'cryptojobslist', 'Blockchain Data Manager', "
            "'Lead digital asset analytics', '[\"crypto\"]', '[]', 'career'), "
            "(3, 'Equipment Co', 'greenhouse', 'Analytics Engineer', "
            "'Optimism about construction', '[\"crypto\"]', '[\"optimism\"]', 'career')"
        ))

    assert maintenance.repair_taxonomy(engine) == 2
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, industry_tags, ecosystem_tags FROM applications ORDER BY id"
        )).fetchall()
    assert rows == [
        (1, "[]", "[]"),
        (2, '["crypto"]', "[]"),
        (3, "[]", "[]"),
    ]


def test_verified_catalog_rotates_without_growing_hot_cache(monkeypatch, tmp_path) -> None:
    ats_discovery = importlib.import_module("job_finder.tools.scrapers._ats_discovery")
    monkeypatch.setattr(ats_discovery, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ats_discovery, "_CACHE_DIR", tmp_path / "ats-cache")
    (tmp_path / "ashby_verified_full.txt").write_text(
        "\n".join(f"company-{i}" for i in range(10)),
        encoding="utf-8",
    )
    first = ats_discovery.verified_rotation_slugs(
        "ashby",
        batch_size=3,
        at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    second = ats_discovery.verified_rotation_slugs(
        "ashby",
        batch_size=3,
        at=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )
    assert len(first) == 3
    assert len(second) == 3
    assert first != second
    # Rotation is ephemeral; only explicit discovery/promotion writes cache.
    assert not (ats_discovery._CACHE_DIR / "ats_discovered_ashby.json").exists()


def test_tags_json_is_stable() -> None:
    assert company_taxonomy.tags_json(["Solana", "crypto", "crypto"]) == json.dumps(
        ["crypto", "solana"], separators=(",", ":")
    )
