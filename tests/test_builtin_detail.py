from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from job_finder.tools.scrapers._utils import _parse_posted_date
from job_finder.company_classifier import (
    classify_job_work_type,
    location_matches_preferences,
)
from job_finder.tools.scrapers.builtin import (
    _hydrate_ambiguous_jobs,
    fetch_builtin_detail,
)


DETAIL_HTML = """
<html><body>
  <div>Posted 4 Hours Ago</div>
  <div id="job-post-body-123" class="html-parsed-content">
    <p><strong>What You'll Do</strong></p>
    <ul><li>Lead a data engineering team.</li><li>Build reliable pipelines.</li></ul>
  </div>
  <a href="https://job-boards.greenhouse.io/example/jobs/123"></a>
</body></html>
"""


SERVE_DETAIL_HTML = r"""
<html><head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [{
      "@type": "JobPosting",
      "title": "Sr. Manager, Data Engineering & Analytics",
      "datePosted": "2026-07-18",
      "jobLocationType": "TELECOMMUTE",
      "jobLocation": [
        {"@type":"Place","address":{"@type":"PostalAddress","addressCountry":"USA"}},
        {"@type":"Place","address":{"@type":"PostalAddress","addressCountry":"CAN","addressLocality":"Toronto","addressRegion":"Ontario"}}
      ],
      "applicantLocationRequirements": [
        {"@type":"Country","name":"USA"},
        {"@type":"Country","name":"CAN"}
      ]
    }]
  }
  </script>
</head><body>
  <div>Reposted 20 Days Ago</div>
  <div id="job-post-body-9414145"><p>Lead Serve Robotics' data team.</p></div>
  <script>
    Builtin.jobPostInit({"job":{"id":9414145,"howToApply":"https://jobs.ashbyhq.com/serverobotics/887ef3a7-3bde-4649-820a-a54b0afc4cf9"}});
  </script>
</body></html>
"""


def test_fetch_builtin_detail_recovers_requirements_date_and_direct_url() -> None:
    with patch(
        "job_finder.tools.scrapers.builtin._fetch_page", return_value=DETAIL_HTML
    ):
        result = fetch_builtin_detail("https://builtin.com/job/example/123")

    assert "Lead a data engineering team." in result["description"]
    # 'Posted 4 Hours Ago' becomes a real date (today) so the freshness
    # filter can parse it; confidence stays fuzzy.
    parsed = _parse_posted_date(result["date_posted"])
    assert parsed is not None
    assert parsed.date() == datetime.now(timezone.utc).date()
    assert result["date_confidence"] == "fuzzy"
    assert result["direct_application_url"] == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )


def test_fetch_builtin_detail_rejects_unrelated_urls_without_network() -> None:
    with patch("job_finder.tools.scrapers.builtin._fetch_page") as fetch:
        assert fetch_builtin_detail("https://example.com/jobs/123") == {}
    fetch.assert_not_called()


def test_fetch_builtin_detail_recovers_structured_multi_location_and_ashby_url() -> None:
    with patch(
        "job_finder.tools.scrapers.builtin._fetch_page",
        return_value=SERVE_DETAIL_HTML,
    ):
        result = fetch_builtin_detail(
            "https://builtin.com/job/sr-manager-data-engineering-analytics/9414145"
        )

    assert result["location"] == "United States; Toronto, Ontario, Canada"
    assert result["is_remote"] is True
    assert result["remote_flag_reported"] is True
    assert result["date_posted"] == "2026-07-18"
    assert result["date_confidence"] == "exact"
    assert result["direct_application_url"] == (
        "https://jobs.ashbyhq.com/serverobotics/"
        "887ef3a7-3bde-4649-820a-a54b0afc4cf9"
    )


def test_serve_multi_location_hydration_survives_la_remote_filter() -> None:
    jobs = [{
        "title": "Sr. Manager, Data Engineering & Analytics",
        "company": "Serve Robotics",
        "location": "6 Locations",
        "url": "https://builtin.com/job/sr-manager-data-engineering-analytics/9414145",
        "source": "builtin",
        "description": "6 Locations · In-Office or Remote",
        "is_remote": True,
    }]
    detail = {
        "description": "Lead Serve Robotics' data team. This role is remote.",
        "location": "United States; Toronto, Ontario, Canada",
        "date_posted": "2026-07-18",
        "date_confidence": "exact",
        "direct_application_url": (
            "https://jobs.ashbyhq.com/serverobotics/"
            "887ef3a7-3bde-4649-820a-a54b0afc4cf9"
        ),
        "is_remote": True,
        "remote_flag_reported": True,
    }
    with patch(
        "job_finder.tools.scrapers.builtin.fetch_builtin_detail",
        return_value=detail,
    ) as fetch:
        assert _hydrate_ambiguous_jobs(jobs) == 1

    fetch.assert_called_once()
    work_type, confidence = classify_job_work_type(jobs[0])
    assert (work_type, confidence) == ("remote", "reported")
    assert location_matches_preferences(
        jobs[0]["location"],
        True,
        preferred_states=["CA"],
        preferred_cities=["Los Angeles"],
        preferred_locations=["Los Angeles, CA"],
        preferred_places=[{
            "city": "Los Angeles",
            "state": "CA",
            "country": "United States",
            "scope": "metro",
        }],
        preferred_countries=["United States"],
        include_remote=True,
        work_type=work_type,
    )


def test_detail_hydration_skips_specific_locations() -> None:
    jobs = [{
        "location": "Los Angeles, CA",
        "url": "https://builtin.com/job/data-manager/123",
    }]
    with patch("job_finder.tools.scrapers.builtin.fetch_builtin_detail") as fetch:
        assert _hydrate_ambiguous_jobs(jobs) == 0
    fetch.assert_not_called()
