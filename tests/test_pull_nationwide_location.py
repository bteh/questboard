"""The PULL-time location filter must not purge US-nationwide roles.

location_matches_preferences runs when "Get new jobs" saves scraped rows and
purges rows that don't match. A bare-country "United States" role is onsite
(no city, not flagged remote), so for an LA seeker it was dropped and never
reached the board, the reason a watched company (BILL) with US-wide roles
stayed missing even after the board read-filter was fixed.
"""

from __future__ import annotations

from job_finder.company_classifier import location_matches_preferences

# What the pull derives for a "Los Angeles, CA" seeker.
US_PREFS = dict(
    preferred_cities=["Los Angeles"],
    preferred_countries=["united states"],
    preferred_places=[{
        "label": "Los Angeles, CA", "kind": "manual", "match_scope": "city",
        "city": "Los Angeles", "region": "CA", "country": "", "country_code": "US",
    }],
    include_remote=True,
)


def test_nationwide_us_role_survives_a_us_city_pull():
    assert location_matches_preferences("United States", False, **US_PREFS) is True


def test_multi_segment_us_role_survives():
    assert location_matches_preferences(
        "Draper, Utah, United States; United States", False, **US_PREFS
    ) is True


def test_specific_other_city_still_purged():
    assert location_matches_preferences("New York, NY", False, **US_PREFS) is False


def test_nationwide_not_inherited_by_a_non_us_seeker():
    uk = dict(
        preferred_cities=["London"],
        preferred_countries=["united kingdom"],
        preferred_places=[{
            "label": "London, UK", "kind": "manual", "match_scope": "city",
            "city": "London", "region": "", "country": "United Kingdom", "country_code": "non-us",
        }],
        include_remote=True,
    )
    assert location_matches_preferences("United States", False, **uk) is False
