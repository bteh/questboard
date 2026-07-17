from __future__ import annotations

from job_finder.tools.scrapers.builtin import _parse_html_jobs


def _card(company: str, date: str, job_id: int) -> str:
    return f"""
    <div data-id="job-card">
      <a data-id="job-card-title" href="/job/data-engineering-manager/{job_id}">
        Data Engineering Manager
      </a>
      <div data-id="company-title"><span>{company}</span></div>
      <span>{company}</span>
      <span>{date}</span>
    </div>
    """


def test_builtin_date_parser_does_not_treat_dragos_as_days_ago() -> None:
    rows = _parse_html_jobs(
        _card("Dragos", "Reposted 4 Hours Ago", 1),
        ["Data Engineering Manager"],
        10,
    )
    assert rows[0]["date_posted"] == "Reposted 4 Hours Ago"
    assert rows[0]["date_confidence"] == "fuzzy"


def test_builtin_enforces_requested_age_after_its_thirty_day_query_bucket() -> None:
    html = _card("Fresh Co", "Reposted 8 Days Ago", 1) + _card(
        "Old Co", "Reposted 25 Days Ago", 2
    )
    rows = _parse_html_jobs(
        html,
        ["Data Engineering Manager"],
        10,
        max_days_old=14,
    )
    assert [row["company"] for row in rows] == ["Fresh Co"]
