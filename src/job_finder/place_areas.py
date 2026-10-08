"""Named places that mean more than one city: metros, valleys, county halves.

The one home for every area table. The board's SQL place filter
(backend application_service.place_filter), the Find Work JobSpy fan-out and
post-search location gate (pipeline, company_classifier), and the part-time
source (scrapers/indeed_parttime) all read from here. Pure data plus pure
string logic: no SQLAlchemy, no backend, no network (tests/test_place_areas.py
pins that).

Matching rules for a job row's location text:
- ``cities`` match as a plain substring (the LA metro's long-standing list).
- ``word_cities`` match only as a whole word on a row that also names a
  ``region`` token (CA / California), and never when one of the city's
  ``WORD_EXCLUDES`` phrases is present. That guard exists because these names
  collide: Orange, NJ; Walnut Creek; Cypress, TX; West Covina vs Covina.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CA = ("ca", "california")


@dataclass(frozen=True)
class Area:
    label: str
    names: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    word_cities: tuple[str, ...] = ()
    region: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()
    radius_miles: int | None = None


# Look-alikes a whole-word match still catches inside California.
WORD_EXCLUDES: dict[str, tuple[str, ...]] = {
    "orange": ("orange county", "orange cove"),
    "walnut": ("walnut creek", "walnut grove", "walnut park"),
    "brea": ("la brea",),
    "covina": ("west covina",),
    "san gabriel": ("san gabriel valley",),
    "pasadena": ("south pasadena",),
    "el monte": ("south el monte",),
    "la habra": ("la habra heights",),
}

SAN_GABRIEL_VALLEY = Area(
    label="San Gabriel Valley (626)",
    names=("san gabriel valley",),
    aliases=("626", "sgv"),
    word_cities=(
        "arcadia", "alhambra", "monterey park", "el monte", "south el monte",
        "san gabriel", "rosemead", "temple city", "san marino", "south pasadena",
        "pasadena", "monrovia", "duarte", "azusa", "covina", "west covina",
        "baldwin park", "irwindale", "city of industry", "industry", "rowland heights",
        "hacienda heights", "walnut", "diamond bar", "la puente", "glendora",
        "sierra madre", "altadena", "san gabriel valley",
    ),
    region=_CA,
    anchors=("El Monte, CA", "Pasadena, CA", "West Covina, CA"),
    radius_miles=10,
)

NORTH_ORANGE_COUNTY = Area(
    label="North Orange County",
    names=("north orange county",),
    aliases=("north oc", "fullerton area"),
    word_cities=(
        "fullerton", "anaheim", "brea", "buena park", "la habra", "placentia",
        "yorba linda", "orange", "cypress", "la palma", "garden grove", "stanton",
    ),
    region=_CA,
    anchors=("Fullerton, CA", "Anaheim, CA"),
    radius_miles=10,
)

# Searchable areas: picked by name, fanned out to anchor cities when searching.
NAMED_AREAS: tuple[Area, ...] = (SAN_GABRIEL_VALLEY, NORTH_ORANGE_COUNTY)

# A board filter keyed to a city name alone drops every metro-sibling city:
# "Los Angeles" would hide Beverly Hills, Santa Monica, Culver City, etc.
# These metros expand on the board; searching still uses the typed place.
# Neighborhood aliases are names a seeker types that boards file under the
# core city (Indeed lists a Koreatown cafe as "Los Angeles, CA", Oct 2026).
# LA word_cities: Bell sits inside Bellflower, Bellevue, and Campbell;
# Commerce, Vernon, Maywood, Downey, Montebello, Highland Park, Eagle Rock,
# Silver Lake, and Koreatown all exist in other states.
METROS: tuple[Area, ...] = (
    Area(
        label="Los Angeles",
        names=("los angeles",),
        aliases=("koreatown", "ktown", "k-town"),
        cities=(
            "los angeles", "beverly hills", "santa monica", "culver city", "pasadena",
            "burbank", "glendale", "long beach", "torrance", "el segundo", "marina del rey",
            "west hollywood", "hollywood", "inglewood", "hawthorne", "manhattan beach",
            "playa vista", "venice", "westwood", "century city", "sherman oaks",
            "studio city", "north hollywood", "van nuys", "woodland hills", "el monte",
            "alhambra", "monterey park", "redondo beach", "santa clarita", "universal city",
            "south gate", "san gabriel", "pico rivera", "huntington park", "east los angeles",
            "echo park", "los feliz", "mid-wilshire", "mid wilshire", "boyle heights",
        ),
        word_cities=(
            "bell", "vernon", "commerce", "maywood", "downey", "montebello",
            "highland park", "eagle rock", "silver lake", "koreatown",
        ),
        region=_CA,
    ),
    Area(
        label="San Francisco",
        names=("san francisco",),
        cities=(
            "san francisco", "oakland", "berkeley", "san mateo", "palo alto", "mountain view",
            "menlo park", "redwood city", "sunnyvale", "santa clara", "san jose", "cupertino",
            "emeryville", "south san francisco", "foster city", "burlingame",
        ),
    ),
    Area(
        label="New York",
        names=("new york",),
        cities=(
            "new york", "brooklyn", "manhattan", "queens", "jersey city", "hoboken",
            "long island city", "newark",
        ),
    ),
    Area(label="Seattle", names=("seattle",),
         cities=("seattle", "bellevue", "redmond", "kirkland", "tacoma")),
    Area(label="Boston", names=("boston",),
         cities=("boston", "cambridge", "somerville", "waltham", "burlington")),
    Area(label="Austin", names=("austin",), cities=("austin", "round rock")),
    Area(label="Chicago", names=("chicago",), cities=("chicago", "evanston")),
    Area(label="Denver", names=("denver",), cities=("denver", "boulder")),
    Area(label="San Diego", names=("san diego",), cities=("san diego", "la jolla", "carlsbad")),
)

# Commute zones for the pipeline's post-search gate (company_classifier): a
# saved city accepts jobs in any city of the same zone. Exact city names,
# matched on the parsed job city.
COMMUTE_METROS: dict[str, set[str]] = {
    "Los Angeles": {"los angeles", "santa monica", "culver city", "burbank", "pasadena", "glendale", "long beach", "torrance", "el segundo", "playa vista", "marina del rey", "venice", "west hollywood", "beverly hills", "inglewood", "hawthorne", "manhattan beach", "hermosa beach", "redondo beach", "woodland hills", "encino", "sherman oaks"},
    "Orange County": {"irvine", "costa mesa", "anaheim", "santa ana", "huntington beach", "newport beach"},
    "San Francisco": {"san francisco", "san jose", "oakland", "palo alto", "mountain view", "sunnyvale", "santa clara", "cupertino", "menlo park", "redwood city", "san mateo", "fremont", "berkeley", "emeryville", "south san francisco", "foster city", "milpitas", "campbell", "los gatos", "saratoga"},
    "New York": {"new york", "brooklyn", "manhattan", "queens", "bronx", "staten island", "jersey city", "hoboken", "newark", "white plains", "stamford", "yonkers"},
    "Seattle": {"seattle", "bellevue", "redmond", "kirkland", "tacoma", "bothell", "renton", "kent", "everett"},
    "Boston": {"boston", "cambridge", "somerville", "quincy", "brookline", "waltham", "newton", "lexington", "burlington"},
    "Austin": {"austin", "round rock", "cedar park", "pflugerville", "georgetown", "san marcos", "kyle"},
    "Chicago": {"chicago", "evanston", "schaumburg", "naperville", "arlington heights", "skokie", "oak brook"},
    "Denver": {"denver", "boulder", "aurora", "lakewood", "littleton", "broomfield", "westminster", "englewood"},
    "San Diego": {"san diego", "la jolla", "chula vista", "carlsbad", "encinitas", "oceanside"},
    "Washington": {"washington", "arlington", "alexandria", "bethesda", "silver spring", "tysons", "reston", "mclean", "fairfax"},
    "Miami": {"miami", "fort lauderdale", "hollywood", "coral gables", "boca raton", "doral", "aventura"},
    "Atlanta": {"atlanta", "decatur", "marietta", "alpharetta", "sandy springs", "roswell", "dunwoody"},
    "Dallas": {"dallas", "fort worth", "plano", "frisco", "irving", "arlington", "richardson", "addison"},
    "Portland": {"portland", "beaverton", "hillsboro", "lake oswego", "tigard"},
    "Minneapolis": {"minneapolis", "st paul", "saint paul", "bloomington", "eden prairie", "plymouth"},
    "Pittsburgh": {"pittsburgh", "carnegie mellon", "oakland"},
    "Detroit": {"detroit", "ann arbor", "dearborn", "troy", "southfield"},
    "Philadelphia": {"philadelphia", "king of prussia", "conshohocken", "cherry hill", "camden"},
    "Raleigh": {"raleigh", "durham", "chapel hill", "cary", "morrisville", "research triangle"},
    "Salt Lake City": {"salt lake city", "provo", "sandy", "draper", "lehi", "orem"},
}

_PLACE_DELIMITERS = (",", "(", ")", "/", "&", ";", "-")
_SINGLE_CA_CITY_RE = re.compile(r"^(?P<city>[a-z .'-]+?)\s*,\s*(?:ca|california)$")


def _squash(text: str) -> str:
    return " ".join((text or "").lower().split())


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) is not None


def named_area_for(place: str) -> Area | None:
    """The searchable area a typed or saved place names, if any."""
    low = _squash(place)
    if not low:
        return None
    for area in NAMED_AREAS:
        if any(name in low for name in area.names) or any(_has_word(low, a) for a in area.aliases):
            return area
    return None


def _single_area_city(place: str) -> Area | None:
    match = _SINGLE_CA_CITY_RE.match(_squash(place).replace(".", ""))
    if not match:
        return None
    city = match.group("city").strip()
    words = ("city of industry", "industry") if city in ("industry", "city of industry") else (city,)
    for area in NAMED_AREAS:
        if city in area.word_cities:
            return Area(label=place.strip(), word_cities=words, region=area.region)
    return None


def area_for(place: str) -> Area | None:
    """What a board place filter should expand to: a named area, a metro, or
    one guarded CA city from a named area ("Arcadia, CA"). None means the
    caller keeps its plain matching."""
    named = named_area_for(place)
    if named:
        return named
    low = _squash(place)
    if not low:
        return None
    for metro in METROS:
        if any(name in low for name in metro.names):
            return metro
    for metro in METROS:
        if any(_has_word(low, alias) for alias in metro.aliases):
            return metro
    return _single_area_city(place)


def padded_location(text: str) -> str:
    """Python twin of the board's SQL padding: dots dropped, list delimiters
    flattened to spaces, a space at each end, so ' word ' is a whole word."""
    out = (text or "").lower().replace(".", "")
    for delimiter in _PLACE_DELIMITERS:
        out = out.replace(delimiter, " ")
    return f" {out} "


def location_in_area(location: str, area: Area) -> bool:
    """Whether a job row's location text sits inside ``area``."""
    low = (location or "").lower()
    if any(city in low for city in area.cities):
        return True
    if not area.word_cities:
        return False
    padded = padded_location(location)
    if area.region and not any(f" {r} " in padded for r in area.region):
        return False
    for word in area.word_cities:
        if f" {word} " not in padded:
            continue
        if not any(f" {ex} " in padded for ex in WORD_EXCLUDES.get(word, ())):
            return True
    return False


def search_places(place: str) -> list[tuple[str, int | None]]:
    """JobSpy (location, radius) pairs for one saved place. A named area runs
    as its anchor cities at the area radius; anything else runs as typed
    with the caller's radius (None)."""
    area = named_area_for(place)
    if area and area.anchors:
        return [(anchor, area.radius_miles) for anchor in area.anchors]
    return [(place, None)]
