"""Every public-employer special case, pinned by the posting that motivated it.

The rules live in job_finder/tools/scrapers/_public_sector.py. Titles and pay
strings below are copied from live EdJoin and CSU Careers responses captured
2026-10-08.
"""

from __future__ import annotations

import pytest

from job_finder.tools.scrapers._public_sector import (
    is_internal_only,
    is_student_only,
    job_type_from,
    money_amounts,
    period_from_words,
    stated_pay_range,
    wants_california,
)


@pytest.mark.parametrize(
    "title",
    [
        "Specialist III:  Tech Support - 11-Month (Current Employees)",
        "Accounting Technician I - Fiscal Services (OPEN TO OUSD EMPLOYEES ONLY)",
        "Research Technician #860 - This position is limited to Classified Employees",
        "Lead Warehouse Worker - (Technology and Information Services Department) "
        "**OPEN TO CURRENT CUSD EMPLOYEES ONLY**",
    ],
)
def test_internal_only_postings_are_closed_to_outside_applicants(title: str) -> None:
    assert is_internal_only(title)


@pytest.mark.parametrize(
    "title",
    [
        "Specialist III:  Tech Support (Outside Candidates)",
        "#26-27-36 Internal Accounting Analyst (District Office)",
        "INFORMATION TECHNOLOGY SYSTEMS ANALYST",
    ],
)
def test_open_postings_stay(title: str) -> None:
    assert not is_internal_only(title)


def test_csu_student_jobs_need_enrollment() -> None:
    assert is_student_only("Student Assistant")
    assert is_student_only("Student Assistant,Student Assistant - Federal Work Study")
    assert is_student_only("Graduate Assistant")
    assert is_student_only("Teaching Associate")
    assert not is_student_only("Staff")
    assert not is_student_only("Instructional Faculty - Temporary/Lecturer,Teaching Associate")
    assert not is_student_only("")


def test_period_is_a_whole_word_so_monday_is_not_daily() -> None:
    # Cal Poly Pomona Administrative Analyst, 2026-10-08
    assert period_from_words(" monthly Work Schedule: Monday") == "monthly"
    assert period_from_words("Per Hour") == "hourly"
    assert period_from_words("Annually") == "annual"
    assert period_from_words("Daily") == "daily"
    assert period_from_words("Monday - Friday") is None
    assert period_from_words("") is None


def test_money_amounts_skip_step_and_range_labels() -> None:
    # Pasadena USD Facilities Technician, Orange USD, Pomona USD, LBUSD
    assert money_amounts("Step 1: $6,586") == [6586.0]
    assert money_amounts("(Range 38) $4,544.00") == [4544.0]
    assert money_amounts("Range 30: $4023.25") == [4023.25]
    assert money_amounts("39.41") == [39.41]
    assert money_amounts("$4,856.16 - $6,197.84") == [4856.16, 6197.84]
    assert money_amounts("") == []


def test_hiring_range_wins_over_classification_band() -> None:
    text = (
        "Job Classification: Administrative Analyst/Specialist Exempt I "
        "Anticipated Hiring Range: $5,274-5,597 monthly Work Schedule: Monday - Friday. "
        "The classification salary range for this position according to the respective "
        "skill level is: minimum $5,274 and maximum $7,684 per month."
    )
    assert stated_pay_range(text) == (5274.0, 5597.0, "monthly")


def test_not_anticipated_to_exceed_range_beats_classification_range() -> None:
    # Cal State Fullerton Technology Support Specialist I
    text = (
        "Salary Range Classification Range $4,595 - $6,694 per month (Hiring range "
        "depending on qualifications, not anticipated to exceed $4,595 - $4,974 per month)"
    )
    assert stated_pay_range(text) == (4595.0, 4974.0, "monthly")


def test_faculty_salary_range_without_period_reads_annual_only_when_it_must() -> None:
    assert stated_pay_range("Salary Range: $90,812 - $94,812 California State") == (
        90812.0, 94812.0, "annual",
    )
    assert stated_pay_range("Salary Range: $4,000 - $5,000 see bulletin") is None


def test_unlabelled_dollar_figures_are_never_pay() -> None:
    # Cal Poly Pomona faculty posting: an H-1B fee is not a salary
    assert stated_pay_range("subject to the $100,000 fee established under") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        # CSU Office of the Chancellor, University Counsel
        (
            "Salary The anticipated salary hiring range is between $229,296 and $242,784 "
            "per year, commensurate with qualifications",
            (229296.0, 242784.0, "annual"),
        ),
        # Cal State East Bay, Postsecondary Program Specialist
        (
            "is anticipated to be in the range of $5,274.00 per month to $6,430.00 per month "
            "(Step 1 to Step 11). Cal State East Bay offers",
            (5274.0, 6430.0, "monthly"),
        ),
        # CSU Monterey Bay, Digital Accessibility Specialist
        (
            "Anticipated Hiring Salary Range: $9,454 (Step 8) to $9,634 (Step 9)* mo. CSU",
            (9454.0, 9634.0, "monthly"),
        ),
        # Cal State San Bernardino, Program Manager
        (
            "Salary: $35.00-$40.00 per hour. Location: CSUSB Campus. 19 hours per week",
            (35.0, 40.0, "hourly"),
        ),
        # Fresno State, Promotions and Fan Engagement Specialist
        (
            "Anticipated Hiring Range : $ 5,178.00 per month (Step 1) CSU Classification "
            "Salary Range : $ 5,178.00 per month (Step 1) - $ 7,543.00 per month",
            (5178.0, 5178.0, "monthly"),
        ),
        # Upward Bound Outreach Coordinator: a stated ceiling, no floor
        (
            "Starting salary placement depends on qualifications and experience and will not "
            "exceed $5,540 a month.",
            (None, 5540.0, "monthly"),
        ),
    ],
)
def test_live_csu_pay_phrasings(text: str, expected) -> None:
    assert stated_pay_range(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Anticipated Hiring Salary Range: $5,507 – $6,677 per course for the Fall 2026 "
        "semester The salary schedule information for the Lecturer – Academic Year",
        "has a salary range of $104-$1,406 per session rate. The hourly rate is",
        "Anticipated Hiring Salary Range: $2,350 per Weighted Teaching Unit (WTU) The "
        "salary schedule information for the Lecturer – Academic Year",
    ],
)
def test_per_unit_pay_is_not_given_a_far_away_period(text: str) -> None:
    assert stated_pay_range(text) is None


def test_hiring_rate_never_borrows_the_band() -> None:
    # Parking Department Coordinator: the hiring rate states no period, so it
    # falls through to the classification band instead of guessing
    text = (
        "Hiring Rate: The hiring rate for this position is $4,367(Step #1) "
        "CSU Classification Salary Range: $4,367 - $6,321 per month"
    )
    assert stated_pay_range(text) == (4367.0, 6321.0, "monthly")


def test_job_type_spelling() -> None:
    assert job_type_from("Full Time") == "fulltime"
    assert job_type_from("Part Time") == "parttime"
    assert job_type_from("Time Varies") == ""


@pytest.mark.parametrize(
    "locations, expected",
    [
        (None, True),
        ([], True),
        (["El Monte, CA"], True),
        (["Fullerton, California"], True),
        (["Arcadia"], True),
        (["Austin, TX"], False),
        (["Remote"], False),
        (["Remote", "Pasadena, CA"], True),
    ],
)
def test_california_gate(locations, expected) -> None:
    assert wants_california(locations) is expected
