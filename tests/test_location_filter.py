"""Tests for location parsing and filtering — reproducing bugs where
India, Missouri (full state name), Mexico, and reversed-order locations
pass through the filter incorrectly.
"""

from __future__ import annotations

import unittest

from job_finder.company_classifier import (
    location_matches_preferences,
    parse_location,
)


class ParseLocationTest(unittest.TestCase):
    """parse_location must handle common scraper formats."""

    def test_city_state_abbreviation(self) -> None:
        """Standard 'City, ST' format."""
        p = parse_location("Los Angeles, CA")
        self.assertEqual(p["city"], "Los Angeles")
        self.assertEqual(p["state"], "CA")

    def test_full_state_name(self) -> None:
        """'City, StateName' — e.g. Workday scraper returns full names."""
        p = parse_location("O'Fallon, Missouri")
        self.assertEqual(p["state"], "MO")
        self.assertIn("Fallon", p["city"])

    def test_full_state_with_country(self) -> None:
        """'City, State, Country' format."""
        p = parse_location("San Jose, California, United States of America")
        self.assertEqual(p["state"], "CA")
        self.assertEqual(p["city"], "San Jose")

    def test_reversed_format(self) -> None:
        """'Country, ST, City' — some scrapers reverse the order."""
        p = parse_location("US, CA, Santa Clara")
        self.assertEqual(p["state"], "CA")
        self.assertEqual(p["city"], "Santa Clara")

    def test_foreign_location(self) -> None:
        """Non-US location should NOT produce a US state."""
        p = parse_location("Hyderabad, India")
        # Should either return empty or a non-US indicator
        # Must NOT pretend this is a US state
        self.assertNotIn(p["state"], {"CA", "IN"})  # IN = Indiana, not India

    def test_foreign_country_mexico(self) -> None:
        p = parse_location("Mexico City, Mexico")
        self.assertNotIn(p["state"], set())  # No US state match
        self.assertEqual(p["city"], "Mexico City")
        self.assertEqual(p["country_name"], "mexico")
        self.assertTrue(p.get("country", "") != "US" or p["state"] == "")

    def test_city_only_location(self) -> None:
        p = parse_location("Seattle")
        self.assertEqual(p["city"], "Seattle")
        self.assertEqual(p["state"], "")

    def test_state_name_only_location(self) -> None:
        p = parse_location("California")
        self.assertEqual(p["state"], "CA")

    def test_country_name_only_location(self) -> None:
        p = parse_location("Germany")
        self.assertEqual(p["country"], "non-us")
        self.assertEqual(p["country_name"], "germany")


class LocationFilterTest(unittest.TestCase):
    """Jobs outside preferred locations should be rejected."""

    def _matches(
        self,
        job_location: str,
        is_remote: bool = False,
        work_type: str = "",
        include_remote: bool = True,
        remote_only: bool = False,
    ) -> bool:
        return location_matches_preferences(
            job_location,
            is_remote,
            preferred_states=["CA"],
            preferred_cities=["Los Angeles"],
            include_remote=include_remote,
            remote_only=remote_only,
            work_type=work_type,
        )

    def test_la_matches(self) -> None:
        self.assertTrue(self._matches("Los Angeles, CA"))

    def test_santa_monica_metro_matches(self) -> None:
        self.assertTrue(self._matches("Santa Monica, CA"))

    def test_remote_always_matches(self) -> None:
        self.assertTrue(self._matches("United States", True, work_type="remote"))

    def test_remote_rejected_when_remote_excluded(self) -> None:
        self.assertFalse(self._matches("United States", True, work_type="remote", include_remote=False))

    def test_india_rejected(self) -> None:
        self.assertFalse(self._matches("Hyderabad, India"))

    def test_missouri_rejected(self) -> None:
        self.assertFalse(self._matches("O'Fallon, Missouri"))

    def test_mexico_rejected(self) -> None:
        self.assertFalse(self._matches("Mexico City, Mexico"))

    def test_san_jose_ca_matches(self) -> None:
        """San Jose is in CA (same state as LA preference)."""
        self.assertTrue(self._matches("San Jose, California, United States of America"))

    def test_santa_clara_reversed_matches(self) -> None:
        self.assertTrue(self._matches("US, CA, Santa Clara"))

    def test_country_preference_matches_non_us_job(self) -> None:
        self.assertTrue(location_matches_preferences(
            "Berlin, Germany",
            False,
            preferred_locations=["Germany"],
        ))

    def test_city_country_preference_matches_non_us_job(self) -> None:
        self.assertTrue(location_matches_preferences(
            "Berlin, Germany",
            False,
            preferred_locations=["Berlin, Germany"],
        ))

    def test_other_country_preference_rejects_non_us_job(self) -> None:
        self.assertFalse(location_matches_preferences(
            "Berlin, Germany",
            False,
            preferred_locations=["France"],
        ))


if __name__ == "__main__":
    unittest.main()
