"""The state parser behind the place filter.

Every case here maps to a real availability string on the board or to a
false-positive the 2026-07-12 filter review confirmed a query-time SQL
tokenizer would produce. Parsing at ingest, in Python, is what makes the
place filter safe; these tests are that safety net.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.us_states import extract_state_codes, state_aliases, state_codes_field  # noqa: E402


class TestExtractAvailabilityLists:
    def test_single_state_only(self) -> None:
        assert extract_state_codes("FL only") == ["FL"]

    def test_ampersand_list(self) -> None:
        assert extract_state_codes("VA & NC only") == ["NC", "VA"]

    def test_long_comma_list_with_dotted_dc_and_and(self) -> None:
        assert extract_state_codes(
            "AL, CT, D.C., MD, VA, WV, FL, NJ, NY, and PA Only"
        ) == ["AL", "CT", "DC", "FL", "MD", "NJ", "NY", "PA", "VA", "WV"]

    def test_slash_separated(self) -> None:
        assert extract_state_codes("VA/NC/MD only") == ["MD", "NC", "VA"]

    def test_semicolon_separated(self) -> None:
        assert extract_state_codes("NY;NJ;VA only") == ["NJ", "NY", "VA"]

    def test_city_state_suffix(self) -> None:
        assert extract_state_codes("Culver City, CA") == ["CA"]

    def test_spelled_out_name(self) -> None:
        assert extract_state_codes("Atlanta, Georgia") == ["GA"]


class TestFalsePositivesTheReviewFound:
    def test_west_virginia_is_not_virginia(self) -> None:
        # the substring trap: "West Virginia" must yield WV, never VA
        assert extract_state_codes("West Virginia") == ["WV"]
        assert extract_state_codes("Charleston, West Virginia") == ["WV"]

    def test_lowercase_prose_words_are_not_codes(self) -> None:
        # "in"/"or"/"me" as English words never become IN/OR/ME
        assert extract_state_codes("office in Austin, TX") == ["TX"]
        assert extract_state_codes("remote or hybrid, Denver, CO") == ["CO"]

    def test_cities_containing_abbreviation_letters(self) -> None:
        # none of these are Georgia, Indiana, or Missouri
        assert extract_state_codes("Chattanooga, TN") == ["TN"]
        assert extract_state_codes("Niagara Falls, NY") == ["NY"]
        assert extract_state_codes("Galveston, TX") == ["TX"]
        assert extract_state_codes("Wilmington, DE") == ["DE"]
        assert extract_state_codes("Baltimore, MD") == ["MD"]

    def test_foreign_and_placeless(self) -> None:
        assert extract_state_codes("Guadalajara") == []
        assert extract_state_codes("Remote") == []
        assert extract_state_codes("nationwide") == []
        assert extract_state_codes("") == []
        assert extract_state_codes(None) == []


class TestMultiWordStates:
    def test_new_york(self) -> None:
        assert extract_state_codes("New York, NY") == ["NY"]
        assert extract_state_codes("New York") == ["NY"]

    def test_new_hampshire_via_ampersand_list(self) -> None:
        assert extract_state_codes("ME, VT & NH") == ["ME", "NH", "VT"]


class TestStateCodesField:
    def test_comma_wrapped_for_token_matching(self) -> None:
        assert state_codes_field("VA & NC only") == ",NC,VA,"
        assert state_codes_field("FL only") == ",FL,"

    def test_empty_when_no_state(self) -> None:
        assert state_codes_field("Guadalajara") == ""
        assert state_codes_field(None) == ""


class TestStateAliases:
    def test_full_name_and_abbreviation_both_resolve(self) -> None:
        assert state_aliases("Georgia") == ("georgia", "GA")
        assert state_aliases("GA") == ("georgia", "GA")
        assert state_aliases("georgia") == ("georgia", "GA")

    def test_dotted_and_spaced(self) -> None:
        assert state_aliases("D.C.") == ("district of columbia", "DC")
        assert state_aliases("New Hampshire") == ("new hampshire", "NH")

    def test_non_state_returns_none(self) -> None:
        assert state_aliases("Culver City") is None
        assert state_aliases("Guadalajara") is None
        assert state_aliases("XY") is None


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
