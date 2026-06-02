"""A city-scoped location preference should accept its metro/commute zone.

Real bug: a user with preferred place "Los Angeles, CA" (scope "city") had every
LA-metro job dropped — Santa Monica, Marina del Rey, Pasadena, Culver City,
El Segundo, Long Beach — because ``_matches_preferred_places`` only ran an exact
``_city_matches_place`` for city-scoped places and never consulted the (already
correct) metro matcher. So BuiltIn LA jobs outside the literal city of
Los Angeles never surfaced. Metro expansion stays bounded to the commute zone
(``METRO_AREAS``), so a different metro in the same state (San Diego, San
Francisco) is still rejected.
"""
from __future__ import annotations

from job_finder.company_classifier import location_matches_preferences as M

LA_PLACE = {
    "label": "Los Angeles, CA", "kind": "city", "match_scope": "city",
    "city": "Los Angeles", "region": "California",
    "country": "United States", "country_code": "US",
}
NYC_PLACE = {
    "label": "New York, NY", "kind": "city", "match_scope": "city",
    "city": "New York", "region": "New York",
    "country": "United States", "country_code": "US",
}


def _la(loc: str, is_remote: bool = False) -> bool:
    return M(loc, is_remote, preferred_places=[LA_PLACE],
             preferred_countries=["United States"], include_remote=True)


def _nyc(loc: str, is_remote: bool = False) -> bool:
    return M(loc, is_remote, preferred_places=[NYC_PLACE],
             preferred_countries=["United States"], include_remote=True)


# LA-metro cities that must now PASS for a "Los Angeles" city preference.
LA_METRO = [
    "Los Angeles, CA, USA",
    "Century City, Los Angeles, CA, USA",
    "Santa Monica, CA, USA",
    "Marina del Rey, CA, USA",
    "Pasadena, CA, USA",
    "Culver City, CA, USA",
    "El Segundo, CA, USA",
    "Long Beach, CA, USA",
    "Burbank, CA, USA",
    "Glendale, CA, USA",
]

# Same state but a DIFFERENT metro — must still be rejected (not a commute zone).
NOT_LA_METRO = [
    "San Diego, CA, USA",
    "San Francisco, CA, USA",
    "Sacramento, CA, USA",
]


def test_la_metro_cities_pass():
    for loc in LA_METRO:
        assert _la(loc) is True, f"LA-metro job should pass: {loc!r}"


def test_other_california_metros_rejected():
    for loc in NOT_LA_METRO:
        assert _la(loc) is False, f"non-LA-metro job should be rejected: {loc!r}"


def test_remote_still_passes():
    assert _la("United States", is_remote=True) is True
    assert _la("Remote", is_remote=True) is True


def test_metro_generalizes_to_nyc():
    assert _nyc("Brooklyn, NY, USA") is True
    assert _nyc("Jersey City, NJ, USA") is True
    assert _nyc("Boston, MA, USA") is False
