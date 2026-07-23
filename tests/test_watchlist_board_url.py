"""Layer 1: paste a careers link, store its exact board token.

Name-guessing can never find boards whose token has nothing to do with
the company name (single-word crypto brands, "xyz" startups). The paste
path recognizes the four supported ATS hosts, stores the token from the
URL verbatim, and verifies it with a single API probe. Anything else is
a 422 with a plain message naming the supported boards.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services import watchlist_service
from app.services.watchlist_service import (
    BoardLookupError,
    UnsupportedBoardUrlError,
    parse_board_url,
    resolve_board_url,
)


# ---------------------------------------------------------------------------
# parse_board_url: pure URL recognition, no network
# ---------------------------------------------------------------------------

RECOGNIZED = [
    ("https://boards.greenhouse.io/acme", ("greenhouse", "acme")),
    ("https://boards.greenhouse.io/Acme/jobs/4021", ("greenhouse", "acme")),
    ("https://job-boards.greenhouse.io/acme/jobs/4021?t=abc", ("greenhouse", "acme")),
    ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", ("greenhouse", "acme")),
    ("https://boards.greenhouse.io/embed/job_app?for=acme&token=99", ("greenhouse", "acme")),
    ("https://jobs.lever.co/acme/9f81-4a2b", ("lever", "acme")),
    ("jobs.lever.co/acme", ("lever", "acme")),  # scheme-less paste
    ("https://jobs.ashbyhq.com/Acme", ("ashby", "acme")),
    ("https://jobs.ashbyhq.com/acme/1234-abcd", ("ashby", "acme")),
    (
        "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        ("workday", "nvidia/NVIDIAExternalCareerSite"),
    ),
    (
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/details/Engineer_JR12",
        ("workday", "nvidia/NVIDIAExternalCareerSite"),
    ),
]


@pytest.mark.parametrize(("url", "expected"), RECOGNIZED)
def test_parse_recognizes_supported_board_urls(url, expected):
    parsed = parse_board_url(url)
    assert parsed is not None, url
    assert (parsed["ats"], parsed["slug"]) == expected


def test_parse_greenhouse_careers_url_is_canonical():
    parsed = parse_board_url("https://job-boards.greenhouse.io/acme/jobs/4021")
    assert parsed["careers_url"] == "https://boards.greenhouse.io/acme"


def test_parse_workday_careers_url_keeps_wd_host_and_site():
    parsed = parse_board_url(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/details/Engineer_JR12"
    )
    assert parsed["careers_url"] == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"


def test_parse_gh_jid_company_page_is_greenhouse_without_token():
    parsed = parse_board_url("https://www.acme.com/careers/opening?gh_jid=4021")
    assert parsed is not None
    assert parsed["ats"] == "greenhouse"
    assert parsed["slug"] == ""


UNRECOGNIZED = [
    "https://www.linkedin.com/company/acme/jobs",
    "https://www.indeed.com/cmp/acme",
    "https://acme.com/careers",
    "not a url",
    "",
]


@pytest.mark.parametrize("url", UNRECOGNIZED)
def test_parse_rejects_everything_else(url):
    assert parse_board_url(url) is None


# ---------------------------------------------------------------------------
# resolve_board_url: exact token + one verification probe
# ---------------------------------------------------------------------------

def test_resolver_stores_exact_token_and_probes_once():
    calls: list[str] = []

    def fake_probe(slug):
        calls.append(slug)
        return {
            "ats": "greenhouse",
            "slug": slug,
            "job_count": 3,
            "careers_url": f"https://boards.greenhouse.io/{slug}",
        }

    with patch.object(watchlist_service, "_try_greenhouse", side_effect=fake_probe):
        result = resolve_board_url("https://boards.greenhouse.io/billcom", name="BILL")

    assert calls == ["billcom"]
    assert result == {
        "name": "BILL",
        "ats": "greenhouse",
        "slug": "billcom",
        "job_count": 3,
        "careers_url": "https://boards.greenhouse.io/billcom",
    }


def test_resolver_rejects_unrecognized_url_naming_supported_boards():
    with pytest.raises(UnsupportedBoardUrlError) as err:
        resolve_board_url("https://www.linkedin.com/company/acme/jobs")
    message = str(err.value)
    for board in ("Greenhouse", "Lever", "Ashby", "Workday"):
        assert board in message


def test_resolver_raises_when_probe_cannot_confirm_board():
    with patch.object(watchlist_service, "_try_lever", return_value=None):
        with pytest.raises(BoardLookupError):
            resolve_board_url("https://jobs.lever.co/acme")


def test_resolver_derives_display_name_when_none_given():
    def fake_probe(slug):
        return {
            "ats": "lever",
            "slug": slug,
            "job_count": 1,
            "careers_url": f"https://jobs.lever.co/{slug}",
        }

    with patch.object(watchlist_service, "_try_lever", side_effect=fake_probe):
        result = resolve_board_url("https://jobs.lever.co/acme-robotics")
    assert result["name"] == "Acme Robotics"


def test_resolver_fetches_board_token_from_gh_jid_page(monkeypatch):
    page_url = "https://www.acme.com/careers/opening?gh_jid=4021"
    html = (
        '<iframe src="https://boards.greenhouse.io/embed/job_app?for=acmebrand&token=4021">'
        "</iframe>"
    )
    fetched: list[str] = []

    class FakeResp:
        status_code = 200
        text = html

    def fake_get(url, *args, **kwargs):
        fetched.append(url)
        return FakeResp()

    probed: list[str] = []

    def fake_probe(slug):
        probed.append(slug)
        return {
            "ats": "greenhouse",
            "slug": slug,
            "job_count": 2,
            "careers_url": f"https://boards.greenhouse.io/{slug}",
        }

    monkeypatch.setattr(watchlist_service.requests, "get", fake_get)
    monkeypatch.setattr(watchlist_service, "_try_greenhouse", fake_probe)

    result = resolve_board_url(page_url, name="Acme")

    assert fetched == [page_url]
    assert probed == ["acmebrand"]
    assert result["slug"] == "acmebrand"
    assert result["ats"] == "greenhouse"


def test_workday_probe_hits_cxs_endpoint(monkeypatch):
    posted: dict = {}

    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"total": 42, "jobs": []}

    def fake_post(url, json=None, headers=None, timeout=None):
        posted["url"] = url
        posted["payload"] = json
        return FakeResp()

    monkeypatch.setattr(watchlist_service.requests, "post", fake_post)

    result = resolve_board_url(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/details/Engineer_JR12"
    )

    assert posted["url"] == (
        "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    )
    assert result["ats"] == "workday"
    assert result["slug"] == "nvidia/NVIDIAExternalCareerSite"
    assert result["job_count"] == 42
    assert result["careers_url"] == "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    assert result["name"] == "Nvidia"


# ---------------------------------------------------------------------------
# API: POST accepts a url and answers 422 for anything unsupported
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.watchlist import router

    # Keep profile YAML writes inside the test sandbox.
    monkeypatch.setattr(watchlist_service, "_PROJECT_ROOT", str(tmp_path))

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_api_add_by_url_stores_confirmed_board(client, monkeypatch):
    def fake_probe(slug):
        return {
            "ats": "greenhouse",
            "slug": slug,
            "job_count": 5,
            "careers_url": f"https://boards.greenhouse.io/{slug}",
        }

    monkeypatch.setattr(watchlist_service, "_try_greenhouse", fake_probe)

    resp = client.post(
        "/profiles/default/watchlist",
        json={"name": "BILL", "url": "https://boards.greenhouse.io/billcom"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == ""
    assert body["companies"] == [
        {
            "name": "BILL",
            "slug": "billcom",
            "ats": "greenhouse",
            "job_count": 5,
            "careers_url": "https://boards.greenhouse.io/billcom",
        }
    ]


def test_api_add_by_unrecognized_url_is_422_with_plain_message(client):
    resp = client.post(
        "/profiles/default/watchlist",
        json={"name": "", "url": "https://www.linkedin.com/company/acme/jobs"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    for board in ("Greenhouse", "Lever", "Ashby", "Workday"):
        assert board in detail


def test_api_add_url_completes_existing_unknown_entry(client, monkeypatch):
    # Seed an inert entry the name-based flow left behind.
    monkeypatch.setattr(
        watchlist_service,
        "discover_company",
        lambda name: {"name": name, "slug": "", "ats": "unknown", "job_count": 0, "careers_url": ""},
    )
    client.post("/profiles/default/watchlist", json={"name": "Umbra"})

    def fake_probe(slug):
        return {
            "ats": "lever",
            "slug": slug,
            "job_count": 4,
            "careers_url": f"https://jobs.lever.co/{slug}",
        }

    monkeypatch.setattr(watchlist_service, "_try_lever", fake_probe)
    resp = client.post(
        "/profiles/default/watchlist",
        json={"name": "Umbra", "url": "https://jobs.lever.co/umbra-hq"},
    )

    assert resp.status_code == 200
    companies = resp.json()["companies"]
    assert len(companies) == 1
    assert companies[0]["name"] == "Umbra"
    assert companies[0]["ats"] == "lever"
    assert companies[0]["slug"] == "umbra-hq"


def test_api_add_url_pasted_into_name_field_still_works(client, monkeypatch):
    def fake_probe(slug):
        return {
            "ats": "ashby",
            "slug": slug,
            "job_count": 2,
            "careers_url": f"https://jobs.ashbyhq.com/{slug}",
        }

    monkeypatch.setattr(watchlist_service, "_try_ashby", fake_probe)
    resp = client.post(
        "/profiles/default/watchlist",
        json={"name": "https://jobs.ashbyhq.com/umbra"},
    )
    assert resp.status_code == 200
    companies = resp.json()["companies"]
    assert companies[0]["ats"] == "ashby"
    assert companies[0]["slug"] == "umbra"
