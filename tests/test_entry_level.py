"""Every entry-level rule, pinned by the posting that motivated it.

Real case (Oct 8 2026): a seeker who lost an IT job looked for analyst and IT
support roles. These titles and description lines are the shapes his
LinkedIn and Indeed searches returned around Los Angeles.
"""

from __future__ import annotations

import pytest

from job_finder.entry_level import (
    DESCRIPTION_RULES,
    TITLE_RULES,
    demands_senior_years,
    entry_level_reason,
    is_entry_level,
)

TITLE_CASES = {
    "junior": "Junior Systems Administrator",
    "associate": "Associate Data Analyst",
    "entry": "Entry Level IT Support Specialist",
    "level one": "Service Desk Analyst - Level 1",
    "trailing I or 1": "IT Support Specialist I (Onsite)",
    "trainee": "IT Trainee",
    "apprentice": "Network Apprentice",
    "assistant": "IT Assistant",
    "technician": "Desktop Support Technician",
    "tier 1": "Tier 1 Service Desk Analyst",
    "help desk": "Help Desk Analyst",
    "intern to hire": "Data Analyst Intern-to-Hire",
}


@pytest.mark.parametrize("rule", [name for name, _ in TITLE_RULES])
def test_each_title_rule_flags_its_real_title(rule: str) -> None:
    assert entry_level_reason(TITLE_CASES[rule]) == f"title: {rule}"


def test_jr_abbreviation_counts_as_junior() -> None:
    assert entry_level_reason("Jr. Data Analyst") == "title: junior"


def test_help_desk_technician_one_is_entry() -> None:
    assert is_entry_level("Help Desk Technician I")


DESCRIPTION_CASES = {
    "0-2 years": "Requirements: 0-2 years of experience in a help desk setting.",
    "1+ year": "1+ year of customer-facing technical support experience.",
    "entry level": "This is an entry-level role on our reporting team.",
    "new grad": "New grads with a CompTIA A+ are welcome to apply.",
    "no experience required": "No experience required, we train on the job.",
}


@pytest.mark.parametrize("rule", [name for name, _ in DESCRIPTION_RULES])
def test_each_description_rule_flags_a_plain_title(rule: str) -> None:
    assert entry_level_reason("Data Analyst", DESCRIPTION_CASES[rule]) == f"description: {rule}"


def test_one_to_three_years_counts_as_entry() -> None:
    assert is_entry_level("Business Analyst", "1-3 years of Excel and SQL.")


def test_plain_title_with_no_signal_is_not_entry() -> None:
    assert not is_entry_level("Data Analyst", "Own weekly reporting for the sales team.")


@pytest.mark.parametrize(
    "title",
    [
        "Senior Help Desk Technician",
        "Help Desk Supervisor",
        "IT Support Lead",
        "Associate Director, Data Analytics",
        "Assistant Manager, IT Operations",
        "Desktop Support Technician II",
        "Sr. Business Analyst",
        "PC Network Support Technician 4",
        "Service Desk Technician (Tier 2)",
        "Help Desk Technician Level 3",
    ],
)
def test_senior_title_word_beats_entry_words(title: str) -> None:
    assert not is_entry_level(title)


@pytest.mark.parametrize(
    "description",
    [
        "Requires 5+ years of experience supporting Windows environments.",
        "Minimum of five years experience as a business analyst.",
        "5-7 years of experience in data analysis.",
        "7 years or more of relevant experience.",
    ],
)
def test_five_plus_years_disqualifies_even_entry_titles(description: str) -> None:
    assert demands_senior_years(description)
    assert not is_entry_level("Help Desk Technician", description)


@pytest.mark.parametrize(
    "description",
    [
        "3-5 years of experience preferred.",
        "Founded 50 years ago in Los Angeles.",
        "Our team has supported 5 years of releases without downtime.",
        "Pay: $5 per hour bonus after 1 year.",
    ],
)
def test_fewer_years_or_unrelated_numbers_do_not_disqualify(description: str) -> None:
    assert not demands_senior_years(description)


def test_entry_level_line_loses_to_five_years() -> None:
    description = "Entry level pay band. 5+ years of SQL required."
    assert not is_entry_level("Data Analyst", description)
