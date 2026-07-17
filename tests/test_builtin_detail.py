from __future__ import annotations

from unittest.mock import patch

from job_finder.tools.scrapers.builtin import fetch_builtin_detail


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


def test_fetch_builtin_detail_recovers_requirements_date_and_direct_url() -> None:
    with patch(
        "job_finder.tools.scrapers.builtin._fetch_page", return_value=DETAIL_HTML
    ):
        result = fetch_builtin_detail("https://builtin.com/job/example/123")

    assert "Lead a data engineering team." in result["description"]
    assert result["date_posted"] == "Posted 4 Hours Ago"
    assert result["date_confidence"] == "fuzzy"
    assert result["direct_application_url"] == (
        "https://job-boards.greenhouse.io/example/jobs/123"
    )


def test_fetch_builtin_detail_rejects_unrelated_urls_without_network() -> None:
    with patch("job_finder.tools.scrapers.builtin._fetch_page") as fetch:
        assert fetch_builtin_detail("https://example.com/jobs/123") == {}
    fetch.assert_not_called()
