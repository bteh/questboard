"""Regression tests for the We Work Remotely RSS scraper.

2026-07-21 audit: the live run finished zero_rows. Probing the feeds showed
WWR reorganized its RSS surface:

- ``/categories/remote-programming-jobs.rss`` no longer serves the
  programming category (it now returns a generic latest-25 mixed feed).
- ``/categories/remote-management-finance-jobs.rss`` is dead: 301 with an
  EMPTY body and NO Location header (requests can't follow it, and 301
  passes ``raise_for_status``, so the parser saw zero bytes).
- The category was renamed ``remote-management-and-finance-jobs``.
- The all-jobs feed moved OUT of /categories/ to
  ``https://weworkremotely.com/remote-jobs.rss`` (100 items).
- Programming split into full-stack / back-end / front-end category feeds.

The fake server below mimics today's live surface: current feed URLs return
real RSS; anything else returns the observed dead 301-with-empty-body. The
old category map gets zero rows against it; the updated map must find jobs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.tools.scrapers.weworkremotely import search_weworkremotely  # noqa: E402


def _rss(*items: tuple[str, str]) -> str:
    rows = "".join(
        f"<item><title>{title}</title><link>{link}</link>"
        f"<description>&lt;p&gt;A remote role.&lt;/p&gt;</description>"
        f"<pubDate>Mon, 20 Jul 2026 12:00:00 +0000</pubDate></item>"
        for title, link in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<rss version=\"2.0\"><channel><title>WWR</title>{rows}</channel></rss>"
    )


# Today's live feed surface (verified by probe on 2026-07-22).
_LIVE_FEEDS: dict[str, str] = {
    "https://weworkremotely.com/remote-jobs.rss": _rss(
        ("Acme: Staff Data Engineer", "https://weworkremotely.com/remote-jobs/acme-staff-data-engineer"),
        ("Umbrella: Customer Support Hero", "https://weworkremotely.com/remote-jobs/umbrella-support"),
    ),
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss": _rss(
        ("Initech: Full Stack Developer", "https://weworkremotely.com/remote-jobs/initech-fullstack"),
    ),
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss": _rss(
        ("Hooli: Senior Data Platform Engineer", "https://weworkremotely.com/remote-jobs/hooli-data-platform"),
    ),
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss": _rss(
        ("Globex: Frontend Engineer", "https://weworkremotely.com/remote-jobs/globex-frontend"),
    ),
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss": _rss(
        ("Stark: DevOps Engineer", "https://weworkremotely.com/remote-jobs/stark-devops"),
    ),
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss": _rss(
        ("Wayne: Data Engineering Manager", "https://weworkremotely.com/remote-jobs/wayne-de-manager"),
    ),
}


def _fake_get(url, **kwargs):
    resp = MagicMock()
    body = _LIVE_FEEDS.get(url)
    if body is not None:
        resp.status_code = 200
        resp.content = body.encode()
    else:
        # Observed live behavior for retired slugs: 301, empty body, no
        # Location header. raise_for_status() does NOT raise on 3xx.
        resp.status_code = 301
        resp.content = b""
    resp.raise_for_status = MagicMock(return_value=None)
    return resp


def _run(roles, categories=None):
    with patch(
        "job_finder.tools.scrapers.weworkremotely.requests.get",
        side_effect=_fake_get,
    ) as mock_get:
        jobs = search_weworkremotely(roles=roles, max_results=50, categories=categories)
    return jobs, [c.args[0] for c in mock_get.call_args_list]


def test_default_categories_hit_live_feed_urls():
    _jobs, urls = _run(roles=None)
    # Every URL requested must exist on today's WWR surface.
    dead = [u for u in urls if u not in _LIVE_FEEDS]
    assert not dead, f"scraper requested retired feed URLs: {dead}"


def test_finds_data_roles_across_default_categories():
    jobs, _urls = _run(roles=["Data Engineering Manager", "Staff Data Engineer"])
    titles = {j["title"] for j in jobs}
    # From the renamed management feed:
    assert "Data Engineering Manager" in titles
    # From the site-wide all-jobs feed:
    assert "Staff Data Engineer" in titles
    # From the split programming feeds (domain match on "data"):
    assert "Senior Data Platform Engineer" in titles


def test_all_category_uses_site_wide_feed():
    jobs, urls = _run(roles=["Staff Data Engineer"], categories=["all"])
    assert "https://weworkremotely.com/remote-jobs.rss" in urls
    assert any(j["title"] == "Staff Data Engineer" for j in jobs)
    assert all(j["source"] == "weworkremotely" for j in jobs)


def test_company_and_title_split():
    jobs, _urls = _run(roles=["Staff Data Engineer"], categories=["all"])
    job = next(j for j in jobs if j["title"] == "Staff Data Engineer")
    assert job["company"] == "Acme"
    assert job["is_remote"] is True
