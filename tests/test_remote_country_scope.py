"""Country-scoped remote filtering: a US user shouldn't see 'Remote - India'.

By default remote jobs always pass (Rule 3). When the user's preferred
locations imply a country (e.g. US states/cities), remote jobs EXPLICITLY
scoped to a different country/region are dropped, while US-scoped, worldwide,
and bare 'Remote' jobs are kept.
"""

from __future__ import annotations

import pytest

from job_finder.company_classifier import location_matches_preferences
from job_finder.pipeline import _resolve_location_filter_preferences

US = ["united states"]
CA = ["CA"]


def _match(loc, *, countries=None, states=CA):
    return location_matches_preferences(
        loc, True, preferred_states=states, preferred_countries=countries
    )


# ── With US country scope: explicit foreign remote drops, US/ambiguous keep ──
@pytest.mark.parametrize("loc", ["Remote, US", "USA Only", "US Only", "Remote (US)",
                                  "Remote - United States", "North America", "Americas"])
def test_us_scoped_remote_kept(loc):
    assert _match(loc, countries=US) is True


@pytest.mark.parametrize("loc", ["Remote - India", "Remote, India", "Remote (EMEA)",
                                  "Europe Only", "Remote - Germany", "APAC", "LATAM"])
def test_foreign_remote_dropped(loc):
    assert _match(loc, countries=US) is False


@pytest.mark.parametrize("loc", ["Remote", "Worldwide", "Anywhere", "Anywhere in the World", ""])
def test_ambiguous_remote_kept(loc):
    assert _match(loc, countries=US) is True


def test_multi_region_including_us_kept():
    # keep-if-any-match: a US-inclusive multi-region remote stays
    assert _match("Remote (US/EU)", countries=US) is True


# ── Backward compatibility: no preferred_countries → remote always passes ──
@pytest.mark.parametrize("loc", ["Remote - India", "Europe Only", "Remote, Germany"])
def test_no_country_scope_keeps_all_remote(loc):
    assert _match(loc, countries=None) is True


def test_non_us_user_keeps_their_country_remote():
    # symmetric: a user targeting India keeps India-remote, drops US-only remote
    assert _match("Remote - India", countries=["india"]) is True
    assert _match("USA Only", countries=["india"]) is False


# ── Deriving preferred_countries from locations ──
def test_resolve_derives_us_from_us_cities():
    result = _resolve_location_filter_preferences(["Los Angeles, CA"], {})
    preferred_countries = result[6]
    assert "united states" in [c.lower() for c in preferred_countries]


def test_resolve_no_scope_for_remote_only():
    result = _resolve_location_filter_preferences(["Remote"], {})
    assert result[6] == []  # no country signal → no scoping (don't over-drop)
