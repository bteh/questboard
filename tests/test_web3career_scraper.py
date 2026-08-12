"""Contracts for the Web3.career API and public-page fallback."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from job_finder.pipeline import _job_salary_passes
from job_finder.tools.scrapers import get_registry
from job_finder.tools.scrapers import web3career as mod


def _public_html(*, include_jsonld: bool = True) -> str:
    structured = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Founding Data Engineer",
        "datePosted": "2026-08-09 10:30:00 +0100",
        "description": "<p>Build Solana analytics pipelines with <b>Kafka</b>.</p>",
        "hiringOrganization": {"@type": "Organization", "name": "Chain Co"},
        "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "USD",
            "value": {
                "@type": "QuantitativeValue",
                "minValue": 180000,
                "maxValue": 220000,
                "unitText": "YEAR",
            },
        },
    }
    script = (
        f'<script type="application/ld+json">{json.dumps(structured)}</script>'
        if include_jsonld else ""
    )
    return f"""
    <html><body>
      <table><tbody>
        <tr class="job-row-grid table_row" data-jobid="152999">
          <td class="cell-main" data-jobid="152999">
            <a data-jobid="152999" href="/founding-data-engineer-chain-co/152999">
              <h2 data-jobid="152999">Founding Data Engineer</h2>
            </a>
            <a data-jobid="152999" href="/founding-data-engineer-chain-co/152999">
              <h3 data-jobid="152999">Chain Co</h3>
            </a>
            <span class="job-location-mobile">📍 Remote</span>
          </td>
          <td class="cell-posted"><time datetime="2026-08-09 10:30:00+01:00">1d</time></td>
          <td class="cell-salary"><p title="Estimated salary based on similar jobs">$180k - $220k</p></td>
          <td class="cell-tags"><a href="/solana-jobs">solana</a><a href="/remote-jobs">remote</a></td>
        </tr>
      </tbody></table>
      {script}
    </body></html>
    """


def _api_job() -> dict:
    return {
        "id": "abc",
        "title": "Senior Data Platform Engineer",
        "company": "Protocol Labs",
        "location": "Remote",
        "remote": True,
        "description": "<p>Build Ethereum data infrastructure.</p>",
        "tags": ["ethereum", "data-science"],
        "apply_url": "https://web3.career/i/required-attribution",
        "url": "https://web3.career/senior-data-platform-engineer/152998",
        "salary": "$190k - $240k",
        "postedAt": "2026-08-10T12:00:00Z",
    }


def test_public_parser_preserves_identity_and_provenance() -> None:
    jobs = mod._parse_public_page(_public_html())

    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] == "Founding Data Engineer"
    assert job["company"] == "Chain Co"
    assert job["url"] == "https://web3.career/founding-data-engineer-chain-co/152999"
    assert job["is_remote"] is True
    assert job["date_confidence"] == "exact"
    assert job["salary_min"] == 180000
    assert job["salary_max"] == 220000
    assert job["salary_source"] == "source_estimate"
    assert job["ecosystem_tags"] == ["solana"]
    assert "Kafka" in job["description"]
    assert "<p>" not in job["description"]


def test_public_card_survives_missing_jsonld_without_cross_job_shift() -> None:
    jobs = mod._parse_public_page(_public_html(include_jsonld=False))
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Founding Data Engineer"
    assert jobs[0]["description"] == ""
    assert jobs[0]["date_posted"] == "2026-08-09 10:30:00+01:00"


def test_public_title_remote_signal_survives_broad_country_location() -> None:
    html = _public_html().replace(
        "Founding Data Engineer", "Remote Founding Data Engineer"
    ).replace("📍 Remote", "📍 United States")
    jobs = mod._parse_public_page(html)
    assert len(jobs) == 1
    assert jobs[0]["location"] == "United States"
    assert jobs[0]["is_remote"] is True


def test_api_parser_handles_documented_mixed_root_and_mandatory_apply_url() -> None:
    raw = mod._extract_api_jobs(["ok", "v1", [_api_job()]])
    assert raw == [_api_job()]

    job = mod._normalize_api_job(raw[0])
    assert job["url"] == "https://web3.career/i/required-attribution"
    assert job["source_listing_url"].endswith("/152998")
    assert job["salary_source"] == "source_estimate"
    assert job["ecosystem_tags"] == ["ethereum"]
    assert job["industry_tags"] == ["crypto"]


def test_token_uses_api_without_touching_public_pages() -> None:
    expected = [mod._normalize_api_job(_api_job())]
    with (
        patch.object(mod, "_search_api", return_value=expected) as api,
        patch.object(mod, "_search_public") as public,
    ):
        jobs = mod.search_web3career(
            roles=["Data Engineer"],
            locations=["Remote"],
            api_token="secret-token",
        )

    assert jobs == expected
    api.assert_called_once()
    public.assert_not_called()


def test_api_failure_falls_back_to_public_pages() -> None:
    expected = mod._parse_public_page(_public_html())
    with (
        patch.object(mod, "_search_api", side_effect=RuntimeError("401")),
        patch.object(mod, "_search_public", return_value=expected) as public,
    ):
        jobs = mod.search_web3career(
            roles=["Data Engineer"],
            api_token="rejected-token",
        )

    assert jobs == expected
    public.assert_called_once()


def test_role_and_remote_routes_are_bounded_and_specific() -> None:
    urls = mod._public_urls(
        ["Founding Data Engineering Manager"],
        ["Los Angeles, CA", "Remote"],
    )
    assert "https://web3.career/data-science-jobs" in urls
    assert "https://web3.career/engineering-manager-jobs" in urls
    assert "https://web3.career/founding-engineer-jobs" in urls
    assert "https://web3.career/remote-jobs" in urls
    assert "https://web3.career/" in urls
    assert len(urls) <= 13


def test_public_requests_explicitly_accept_html() -> None:
    assert "text/html" in mod._PUBLIC_HEADERS["Accept"]
    assert mod._PUBLIC_HEADERS["Accept"] != mod._HEADERS["Accept"]


def test_source_estimate_never_excludes_a_job_at_the_salary_floor() -> None:
    assert _job_salary_passes(
        {
            "salary_min": 100000,
            "salary_max": 120000,
            "salary_currency": "USD",
            "salary_period": "annual",
            "salary_source": "source_estimate",
        },
        190000,
        "USD",
    )


def test_registry_and_default_configs_enable_web3career() -> None:
    meta = get_registry()["web3career"]
    assert meta.display_name == "Web3.career"
    assert meta.category == "crypto"
    assert meta.full_snapshot is False
    assert meta.stale_after_days == 45

    root = Path(__file__).resolve().parents[1]
    for path in (
        root / "src/job_finder/config/search_config.yaml",
        root / "src/job_finder/config/profiles/default.yaml",
        root / "backend/config/search_config.yaml",
    ):
        text = path.read_text(encoding="utf-8")
        assert "web3career" in text
