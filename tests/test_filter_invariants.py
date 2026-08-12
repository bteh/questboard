"""Property / invariant tests for the board's real filter predicates.

Each bug this session violated one rule that a filter must ALWAYS obey. These
tests generate a matrix of inputs and assert the rule holds for every one, so
the next place_filter or freshness regression fails here before it ships.

They exercise the production predicates directly (no re-implementation):
  application_service.place_filter / stated_pay_filter / board_filter_conditions
  local_agent_service._source_age_days / _title_is_in_lane
against generated rows in a throwaway in-memory SQLite DB, using the same
create_engine + Base.metadata.create_all harness as tests/test_nationwide_location.py.

No hypothesis: generators are hand-rolled loops over curated value lists.
"""

from __future__ import annotations

import itertools
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "src")):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from app.services.application_service import (  # noqa: E402
    board_filter_conditions,
    place_filter,
    stated_pay_filter,
)
from app.services.local_agent_service import (  # noqa: E402
    _source_age_days,
    _title_is_in_lane,
)
from job_finder.models.database import ApplicationRecord, Base  # noqa: E402
from job_finder.us_states import state_codes_field  # noqa: E402


# --------------------------------------------------------------------------- #
# Harness helpers
# --------------------------------------------------------------------------- #

# A shared engine per test is overkill; each test builds its own in-memory DB so
# generated rows never leak between invariants. StaticPool keeps the single
# in-memory connection alive for the life of the engine (the Session holds the
# bind), so schema + rows survive across queries in one test.
def _fresh_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


_COUNTER = itertools.count()


def _add(
    s: Session,
    *,
    job_title: str | None = None,
    location=" ",
    is_remote: bool = False,
    remote_scope: str = "",
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_currency: str = "",
    salary_period: str = "",
    salary_min_annualized: float | None = None,
    salary_max_annualized: float | None = None,
    state_codes: str | None = None,
    company: str = "Acme",
) -> ApplicationRecord:
    """Insert one generated row and return it (flushed, queryable)."""
    n = next(_COUNTER)
    if job_title is None:
        job_title = f"row-{n}"
    # A sentinel default distinguishes "caller did not set location" from an
    # explicit None (placeless) or "" (placeless). Only real strings feed
    # state_codes.
    if location == " ":
        location = ""
    if state_codes is None:
        state_codes = state_codes_field(location) if location else ""
    row = ApplicationRecord(
        job_title=job_title,
        company=company,
        job_url=f"https://x.example/{n}",
        location=location,
        is_remote=is_remote,
        remote_scope=remote_scope,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_period=salary_period,
        salary_min_annualized=salary_min_annualized,
        salary_max_annualized=salary_max_annualized,
        state_codes=state_codes,
        vertical="career",
    )
    s.add(row)
    s.flush()
    return row


def _place_matches(s: Session, location, strict: bool = False) -> set[str]:
    cond = place_filter(ApplicationRecord, location, location_strict=strict)
    q = s.query(ApplicationRecord)
    if cond is not None:
        q = q.filter(cond)
    return {r.job_title for r in q.all()}


def _pay_passes(
    s: Session,
    title: str,
    salary_min=None,
    salary_max=None,
    salary_currency=None,
) -> bool:
    cond = stated_pay_filter(
        ApplicationRecord,
        salary_min,
        salary_max,
        salary_currency,
    )
    q = s.query(ApplicationRecord).filter(ApplicationRecord.job_title == title)
    if cond is not None:
        q = q.filter(cond)
    return q.count() >= 1


def test_staffing_preference_uses_the_same_board_predicate() -> None:
    s = _fresh_session()
    _add(s, company="Jobgether", job_title="Data Engineering Manager")
    _add(s, company="Eleven Recruiting", job_title="Data Engineering Manager")
    _add(s, company="Stripe", job_title="Data Engineering Manager")
    conditions = board_filter_conditions(
        ApplicationRecord,
        exclude_staffing_agencies=True,
    )
    rows = s.query(ApplicationRecord).filter(*conditions).all()
    assert {row.company for row in rows} == {"Stripe"}


# --------------------------------------------------------------------------- #
# Curated generator value lists
# --------------------------------------------------------------------------- #

US_CITY_SEEKERS = [
    "Los Angeles", "San Francisco", "Seattle", "Boston",
    "Austin", "Chicago", "Denver", "San Diego", "New York",
]
US_STATE_SEEKERS = [
    "California", "Texas", "Georgia", "Florida", "Washington", "TX", "CA", "GA",
]
US_COUNTRY_SEEKERS = ["United States", "USA", "US", "United States of America"]
NON_US_SEEKERS = ["London", "Toronto", "Guadalajara", "Berlin", "Sydney"]

ALL_SEEKERS = US_CITY_SEEKERS + US_STATE_SEEKERS + NON_US_SEEKERS + US_COUNTRY_SEEKERS

# Scopes that are NOT international-only. The place filter drops a remote row
# whose scope is 'intl' (remote only for another country), so those are the
# real product exception and are excluded from the "remote always reachable"
# invariant on purpose.
NON_INTL_SCOPES = ["", "us", "worldwide"]


# --------------------------------------------------------------------------- #
# Invariant 1: reachability never hides work-from-anywhere
# --------------------------------------------------------------------------- #

# Locations that carry a genuine remote signal the SQL looks for.
REMOTE_SIGNAL_LOCATIONS = [
    "Remote",
    "Fully Remote",
    "Remote - US",
    "Work from anywhere",
    "Online",
    "Nationwide",
]
# Foreign-looking places that are reachable only because is_remote=True.
REMOTE_FLAG_LOCATIONS = [
    "London, UK",
    "Bangalore, India",
    "Paris, France",
    "Toronto, Canada",
]


def test_invariant_1_remote_is_never_hidden():
    """A row with a genuine remote signal (or is_remote=True) and a non-intl
    scope is kept by non-strict place_filter for EVERY seeker place."""
    s = _fresh_session()
    remote_rows: list[ApplicationRecord] = []
    # (1a) explicit remote wording x non-intl scope
    for loc in REMOTE_SIGNAL_LOCATIONS:
        for scope in NON_INTL_SCOPES:
            remote_rows.append(_add(s, location=loc, remote_scope=scope))
    # (1b) is_remote=True with a foreign location, still reachable
    for loc in REMOTE_FLAG_LOCATIONS:
        for scope in NON_INTL_SCOPES:
            remote_rows.append(_add(s, location=loc, is_remote=True, remote_scope=scope))

    combos = 0
    for seeker in ALL_SEEKERS:
        got = _place_matches(s, seeker)
        for r in remote_rows:
            combos += 1
            assert r.job_title in got, (
                f"remote row hidden: title={r.job_title!r} loc={r.location!r} "
                f"is_remote={r.is_remote} scope={r.remote_scope!r} seeker={seeker!r}"
            )
    # (rows x seekers) = 30 x 26 = 780 assertions
    assert combos == len(remote_rows) * len(ALL_SEEKERS)


# --------------------------------------------------------------------------- #
# Invariant 2: placeless is never hidden
# --------------------------------------------------------------------------- #

def test_invariant_2_placeless_is_never_hidden():
    """A row with location NULL or "" passes non-strict place_filter for every
    seeker place, regardless of remote flags."""
    s = _fresh_session()
    placeless: list[ApplicationRecord] = []
    for loc in (None, ""):
        for is_remote, scope in ((False, ""), (True, "worldwide")):
            placeless.append(
                _add(s, location=loc, is_remote=is_remote, remote_scope=scope)
            )

    combos = 0
    for seeker in ALL_SEEKERS:
        got = _place_matches(s, seeker)
        for r in placeless:
            combos += 1
            assert r.job_title in got, (
                f"placeless row hidden: title={r.job_title!r} loc={r.location!r} "
                f"seeker={seeker!r}"
            )
    # 4 rows x 26 seekers = 104 assertions
    assert combos == len(placeless) * len(ALL_SEEKERS)


# --------------------------------------------------------------------------- #
# Invariant 3: US-nationwide reachability
# --------------------------------------------------------------------------- #

US_NATIONWIDE_LOCATIONS = [
    "United States",
    "USA",
    "US",
    "United States of America",
    "u.s.",
    "u.s.a.",
    # a nationwide option as the trailing segment of a multi-place list
    "Draper, Utah, United States; United States",
]

# (seeker city, other-city posting) pairs verified to share no metro city, so
# the posting is a genuine mismatch that must be filtered.
NEGATIVE_CITY_PAIRS = [
    ("Los Angeles", "New York, United States"),
    ("Boston", "Los Angeles, United States"),
    ("Seattle", "Chicago, United States"),
    ("Denver", "Miami, United States"),
    ("San Diego", "Austin, United States"),
    ("Chicago", "Seattle, United States"),
    ("San Francisco", "Boston, United States"),
    ("Austin", "Denver, United States"),
]


def test_invariant_3_us_nationwide_reachable_for_us_seekers():
    """A bare-country US location is reachable from any US city or state."""
    s = _fresh_session()
    nationwide_rows = [_add(s, location=loc) for loc in US_NATIONWIDE_LOCATIONS]

    us_seekers = US_CITY_SEEKERS + US_STATE_SEEKERS
    combos = 0
    for seeker in us_seekers:
        got = _place_matches(s, seeker)
        for r in nationwide_rows:
            combos += 1
            assert r.job_title in got, (
                f"US-nationwide row hidden: loc={r.location!r} for US seeker {seeker!r}"
            )
    # 7 locations x 17 US seekers = 119 assertions
    assert combos == len(nationwide_rows) * len(us_seekers)


def test_invariant_3_specific_other_city_is_filtered():
    """A specific out-of-metro city ('<other>, United States') does NOT pass
    for a mismatched seeker city, even though the seeker is US."""
    s = _fresh_session()
    # one row per pair, unique title, so a shared session cannot cross-contaminate
    rows = {}
    for i, (_seeker, other) in enumerate(NEGATIVE_CITY_PAIRS):
        rows[i] = _add(s, job_title=f"neg-{i}", location=other)
    # a real nationwide row lives alongside them and MUST stay reachable
    nationwide = _add(s, job_title="nationwide-control", location="United States")

    for i, (seeker, other) in enumerate(NEGATIVE_CITY_PAIRS):
        got = _place_matches(s, seeker)
        assert rows[i].job_title not in got, (
            f"mismatched city leaked: {other!r} reached seeker {seeker!r}"
        )
        assert nationwide.job_title in got, (
            f"nationwide control hidden for US seeker {seeker!r}"
        )


# --------------------------------------------------------------------------- #
# Invariant 4: no place set -> the place filter adds nothing (never empties)
# --------------------------------------------------------------------------- #

LOCATION_POOL = [
    "Los Angeles, CA", "New York, United States", "United States", "Remote",
    "London, UK", "Austin, Texas", "", None, "Online", "Chicago, IL",
    "Berlin, Germany", "Seattle, WA", "USA", "Nationwide",
]


def test_invariant_4_no_place_never_empties_the_set():
    """board_filter_conditions(location=None) must add no location condition, so
    a non-empty set stays exactly as large. Asserted over several generated
    row batches."""
    assert place_filter(ApplicationRecord, None) is None
    # and with no other filters, the condition list is empty
    assert board_filter_conditions(ApplicationRecord, location=None) == []
    # contrast: a real place DOES add a condition (proves the check bites)
    assert board_filter_conditions(ApplicationRecord, location="Los Angeles")

    batches = 8
    for b in range(batches):
        s = _fresh_session()
        # deterministic batch: rotate the pool so batches differ
        size = 6 + (b % 6)
        locs = [LOCATION_POOL[(b * 3 + k) % len(LOCATION_POOL)] for k in range(size)]
        for loc in locs:
            _add(s, location=loc)
        total = s.query(ApplicationRecord).count()
        assert total == size

        conds = board_filter_conditions(ApplicationRecord, location=None)
        assert conds == [], f"batch {b}: location=None produced conditions {conds!r}"
        q = s.query(ApplicationRecord)
        for c in conds:
            q = q.filter(c)
        assert q.count() == total, (
            f"batch {b}: location=None changed the count {total} -> {q.count()}"
        )


# --------------------------------------------------------------------------- #
# Invariant 5: unknown pay is always kept
# --------------------------------------------------------------------------- #

PAY_FLOORS = [None, 0, 20, 60000, 150000, 300000]
PAY_CEILINGS = [None, 1, 100, 100000, 250000]
# non-session periods, so a pass proves it is the None/None that keeps the row
UNKNOWN_PERIODS = ["", "yearly", "monthly", None]


def test_invariant_5_unknown_pay_is_always_kept():
    """salary_min=None and salary_max=None passes stated_pay_filter for every
    floor/ceiling combination, whatever the (non-session) period."""
    s = _fresh_session()
    unknown_rows = [
        _add(s, salary_min=None, salary_max=None, salary_period=(p or ""))
        for p in UNKNOWN_PERIODS
    ]

    combos = 0
    for floor in PAY_FLOORS:
        for ceiling in PAY_CEILINGS:
            if floor is None and ceiling is None:
                continue  # no filter at all; nothing to prove
            for r in unknown_rows:
                combos += 1
                assert _pay_passes(s, r.job_title, floor, ceiling), (
                    f"unknown-pay row dropped: title={r.job_title!r} "
                    f"period={r.salary_period!r} floor={floor} ceiling={ceiling}"
                )
    # 29 floor/ceiling combos x 4 unknown rows = 116 assertions
    assert combos == (len(PAY_FLOORS) * len(PAY_CEILINGS) - 1) * len(unknown_rows)


def test_invariant_5_unlike_or_missing_currency_is_not_compared_as_usd():
    s = _fresh_session()
    usd = _add(
        s,
        job_title="usd-low",
        salary_min=90_000,
        salary_max=90_000,
        salary_currency="USD",
    )
    eur = _add(
        s,
        job_title="eur-not-comparable",
        salary_min=90_000,
        salary_max=90_000,
        salary_currency="EUR",
    )
    unstated = _add(
        s,
        job_title="currency-unstated",
        salary_min=90_000,
        salary_max=90_000,
    )

    assert not _pay_passes(s, usd.job_title, 120_000, None, "USD")
    assert _pay_passes(s, eur.job_title, 120_000, None, "USD")
    assert _pay_passes(s, unstated.job_title, 120_000, None, "USD")


# --------------------------------------------------------------------------- #
# Invariant 6: pay period sanity (annualization + session survival)
# --------------------------------------------------------------------------- #

HOURLY_RATES = list(range(20, 91, 5))  # 20, 25, ... 90
PERIOD_MULT = {"hourly": 2080, "daily": 260, "weekly": 52, "monthly": 12}


def test_invariant_6_hourly_rate_is_judged_annualized():
    """An hourly rate is judged on its annualized value: it clears a floor it
    would fail as a raw number, and fails a floor above its annual figure."""
    s = _fresh_session()
    for r in HOURLY_RATES:
        annual = r * PERIOD_MULT["hourly"]
        hourly = _add(
            s, job_title=f"hourly-{r}", salary_min=float(r), salary_max=float(r),
            salary_period="hourly",
        )
        # a twin with no period: the SAME raw numbers, judged as-is
        raw = _add(
            s, job_title=f"raw-{r}", salary_min=float(r), salary_max=float(r),
            salary_period="",
        )
        # raw r (<=90) is below a 200 floor; annualized r*2080 (>=41600) clears it
        assert _pay_passes(s, hourly.job_title, 200, None), (
            f"hourly {r}/hr dropped by a 200 floor it clears once annualized"
        )
        assert not _pay_passes(s, raw.job_title, 200, None), (
            f"raw {r} unexpectedly cleared a 200 floor without annualization"
        )
        # judged ON the annual value: passes at the boundary, fails just above
        assert _pay_passes(s, hourly.job_title, annual, None), (
            f"hourly {r}/hr failed floor == its own annual {annual}"
        )
        assert not _pay_passes(s, hourly.job_title, annual + PERIOD_MULT["hourly"], None), (
            f"hourly {r}/hr passed a floor above its annual {annual}"
        )
    # 15 rates x 4 assertions = 60


def test_invariant_6_daily_weekly_monthly_annualize():
    """Daily/weekly/monthly rates annualize by their multiplier."""
    s = _fresh_session()
    combos = 0
    for period in ("daily", "weekly", "monthly"):
        mult = PERIOD_MULT[period]
        for rate in (100, 400, 2000):
            annual = rate * mult
            row = _add(
                s, job_title=f"{period}-{rate}", salary_min=float(rate),
                salary_max=float(rate), salary_period=period,
            )
            combos += 1
            assert _pay_passes(s, row.job_title, annual, None), (
                f"{period} {rate} failed floor == annual {annual}"
            )
            assert not _pay_passes(s, row.job_title, annual + mult, None), (
                f"{period} {rate} passed a floor above annual {annual}"
            )
    assert combos == 9


def test_invariant_6_annualized_column_wins_over_raw():
    """When the parser already annualized, coalesce prefers that column."""
    s = _fresh_session()
    row = _add(
        s, job_title="pre-annualized", salary_min=5.0, salary_max=5.0,
        salary_period="hourly", salary_min_annualized=150000.0,
        salary_max_annualized=150000.0,
    )
    assert _pay_passes(s, row.job_title, 140000, None)
    assert not _pay_passes(s, row.job_title, 160000, None)


SESSION_AMOUNTS = [50, 200, 1000]
SESSION_FLOORS = [0, 60000, 150000, 500000]
SESSION_CEILINGS = [None, 1, 100, 100000]


def test_invariant_6_session_pay_never_dropped():
    """Per-gig 'session' pay is not a rate, so no annual floor or ceiling drops
    it (kept like no-stated-pay)."""
    s = _fresh_session()
    session_rows = [
        _add(s, job_title=f"session-{amt}", salary_min=float(amt),
             salary_max=float(amt), salary_period="session")
        for amt in SESSION_AMOUNTS
    ]

    combos = 0
    for r in session_rows:
        for floor in SESSION_FLOORS:
            for ceiling in SESSION_CEILINGS:
                combos += 1
                assert _pay_passes(s, r.job_title, floor, ceiling), (
                    f"session row dropped: title={r.job_title!r} "
                    f"floor={floor} ceiling={ceiling}"
                )
    # 3 amounts x 4 floors x 4 ceilings = 48
    assert combos == len(SESSION_AMOUNTS) * len(SESSION_FLOORS) * len(SESSION_CEILINGS)


# --------------------------------------------------------------------------- #
# Invariant 7: freshness monotonicity and anchoring (_source_age_days)
# --------------------------------------------------------------------------- #

_TOL = 1e-4  # days (~8.6s): generous slack for clock drift between now() calls

ISO_DATES = [
    "2019-03-01",
    "2021-06-15",
    "2023-12-31",
    "2024-01-01T12:00:00Z",
    "2018-11-11",
]


def test_invariant_7a_absolute_date_ignores_anchor():
    """An absolute ISO date's age does not depend on any anchor."""
    now = datetime.now(timezone.utc)
    anchors = [
        None,
        now - timedelta(days=1),
        now - timedelta(days=365),
        (now - timedelta(days=5)).isoformat(),
        "not-a-real-date",  # even an unparseable anchor is ignored for ISO
    ]
    combos = 0
    for iso in ISO_DATES:
        base = _source_age_days(iso, None)
        assert base is not None
        for anchor in anchors:
            combos += 1
            got = _source_age_days(iso, anchor)
            assert got is not None and abs(got - base) < _TOL, (
                f"ISO {iso!r} age moved with anchor {anchor!r}: {got} vs {base}"
            )
    # 5 dates x 5 anchors = 25
    assert combos == len(ISO_DATES) * len(anchors)


REL_OFFSETS_N = [0, 1, 3, 7, 14, 30]
ANCHOR_AGES_K = [0, 1, 5, 10, 30]


def test_invariant_7b_relative_prose_is_anchor_plus_offset():
    """'N days ago' anchored on date_found reads age = anchor_age + N, so a
    fixed prose row can only get OLDER as date_found recedes."""
    now = datetime.now(timezone.utc)
    combos = 0
    for k in ANCHOR_AGES_K:
        anchor = now - timedelta(days=k)
        for n in REL_OFFSETS_N:
            for phrasing in (f"{n} days ago", f"Reposted {n} Days Ago"):
                combos += 1
                got = _source_age_days(phrasing, anchor)
                assert got is not None and abs(got - (k + n)) < _TOL, (
                    f"prose {phrasing!r} anchor_age={k}: got {got}, want {k + n}"
                )
    # also the yesterday/today shorthands
    for k in ANCHOR_AGES_K:
        anchor = now - timedelta(days=k)
        assert abs(_source_age_days("yesterday", anchor) - (k + 1)) < _TOL
        assert abs(_source_age_days("today", anchor) - (k + 0)) < _TOL
    # 5 anchors x 6 offsets x 2 phrasings = 60
    assert combos == len(ANCHOR_AGES_K) * len(REL_OFFSETS_N) * 2


def test_invariant_7b_prose_row_only_gets_older():
    """Monotonicity: for a fixed prose string, older date_found => older age."""
    now = datetime.now(timezone.utc)
    for phrasing in ("3 days ago", "Reposted 7 Days Ago", "yesterday"):
        ks = [0, 1, 5, 10, 30, 90]
        ages = [_source_age_days(phrasing, now - timedelta(days=k)) for k in ks]
        assert all(a is not None for a in ages)
        for i in range(len(ages) - 1):
            assert ages[i] < ages[i + 1], (
                f"{phrasing!r} not monotonic across date_found: {list(zip(ks, ages))}"
            )


PROSE_STRINGS = [
    "3 days ago",
    "reposted 5 days ago",
    "yesterday",
    "today",
    "2 hours ago",
    "30 minutes ago",
]


def test_invariant_7c_prose_without_anchor_is_unknown():
    """Relative prose with no readable anchor returns None (never eternally
    fresh)."""
    combos = 0
    for prose in PROSE_STRINGS:
        for anchor in (None, "not-a-date", ""):
            combos += 1
            assert _source_age_days(prose, anchor) is None, (
                f"prose {prose!r} with anchor {anchor!r} returned a fake age"
            )
    # 6 prose x 3 unreadable anchors = 18
    assert combos == len(PROSE_STRINGS) * 3


# --------------------------------------------------------------------------- #
# Invariant 8: strict place_filter is always a subset of non-strict
# --------------------------------------------------------------------------- #

def _seed_diverse(s: Session) -> None:
    _add(s, job_title="la-core", location="Los Angeles, CA")
    _add(s, job_title="la-sibling", location="Santa Monica, CA")
    _add(s, job_title="sf-core", location="San Francisco, CA")
    _add(s, job_title="sf-sibling", location="Oakland, CA")
    _add(s, job_title="nyc-core", location="New York, NY")
    _add(s, job_title="tx-city", location="Austin, Texas, United States")
    _add(s, job_title="ga-only", location="VA, GA & NC only")
    _add(s, job_title="wv-trap", location="Charleston, West Virginia")
    _add(s, job_title="remote-plain", location="Remote")
    _add(s, job_title="remote-online", location="Online")
    _add(s, job_title="nationwide", location="Nationwide")
    _add(s, job_title="anywhere", location="Work from anywhere")
    _add(s, job_title="remote-flag", location="London, UK", is_remote=True, remote_scope="worldwide")
    _add(s, job_title="remote-intl", location="Remote (UK only)", is_remote=True, remote_scope="intl")
    _add(s, job_title="bare-us", location="United States")
    _add(s, job_title="bare-usa", location="USA")
    _add(s, job_title="nyc-us", location="New York, United States")
    _add(s, job_title="placeless-null", location=None)
    _add(s, job_title="placeless-empty", location="")
    _add(s, job_title="london", location="London, UK")
    _add(s, job_title="berlin", location="Berlin, Germany")
    _add(s, job_title="toronto", location="Toronto, Canada")


def test_invariant_8_strict_is_a_subset_of_nonstrict():
    """Anything strict place_filter keeps, non-strict keeps too (place_match is
    one disjunct of the non-strict OR). Over generated rows and seekers."""
    s = _fresh_session()
    _seed_diverse(s)

    seekers = US_CITY_SEEKERS + US_STATE_SEEKERS + NON_US_SEEKERS + US_COUNTRY_SEEKERS
    saw_proper_subset = False
    for seeker in seekers:
        strict = _place_matches(s, seeker, strict=True)
        loose = _place_matches(s, seeker, strict=False)
        leaked = strict - loose
        assert not leaked, (
            f"strict kept rows non-strict dropped for seeker {seeker!r}: {sorted(leaked)}"
        )
        if strict < loose:
            saw_proper_subset = True
    # sanity: non-strict genuinely keeps MORE somewhere (remote/placeless), so
    # the subset relation is not vacuously an equality everywhere.
    assert saw_proper_subset, "expected non-strict to keep more than strict for some seeker"


# --------------------------------------------------------------------------- #
# Invariant 9 (bonus): _title_is_in_lane stays recall-safe and conflict-aware
# --------------------------------------------------------------------------- #

LANE_ROLES = [
    "Data Engineer", "Software Engineer", "Product Manager", "Data Analyst",
    "Machine Learning Engineer", "Platform Engineer", "Data Scientist",
    "Manager", "Director",
]
LEVEL_WORDS = ["Senior", "Staff", "Principal", "Junior", "Associate"]


def test_invariant_9_title_lane_recall_and_conflicts():
    """A role is always in its own lane, seniority levels never drop a match,
    and an occupation conflict the query lacks is excluded."""
    # reflexivity + level-invariance
    combos = 0
    for role in LANE_ROLES:
        assert _title_is_in_lane(role, [role]), f"{role!r} not in its own lane"
        for lvl in LEVEL_WORDS:
            combos += 1
            leveled = f"{lvl} {role}"
            assert _title_is_in_lane(leveled, [role]), (
                f"{leveled!r} dropped from lane of {role!r}"
            )
    # conflict exclusion: a clinical/product/program tie the engineer query
    # does not share must NOT count as in-lane
    engineer_query = ["Data Engineer"]
    for conflicting in (
        "Clinical Research Nurse",
        "Product Manager",
        "Program Manager",
        "Clinical Data Specialist",
    ):
        assert not _title_is_in_lane(conflicting, engineer_query), (
            f"{conflicting!r} wrongly counted in the Data Engineer lane"
        )
    # 9 roles x 5 levels = 45 level assertions
    assert combos == len(LANE_ROLES) * len(LEVEL_WORDS)


def test_invariant_9b_team_name_suffix_does_not_poison_the_lane():
    """Big companies format titles as "Role, Team - Org". The Aug 2026 audit
    found "Principal Data Engineer, Personalization - Central Product
    Insights" (Netflix) hidden from every saved role because "Product" in the
    TEAM name read as a Product Manager conflict, and "Data Engineer (Cleared)
    - DoD Program - Remote" hidden by "Program". An occupation word only
    conflicts in the segment that names the role, not in an org qualifier."""
    q = ["Staff Data Engineer"]
    for hidden_real_match in (
        "Principal Data Engineer, Personalization - Central Product Insights",
        "Data Engineer (Cleared) - DoD Program - Remote",
        "Staff Software Engineer, Data Products",
    ):
        assert _title_is_in_lane(hidden_real_match, q), (
            f"{hidden_real_match!r} is a real data-engineering role"
        )
    for still_conflicting in (
        # The occupation word IS the role here.
        "Senior Staff Product Manager, AI Platform",
        "Program Manager, Foundation Data and Operations",
        # Generic-only first segment: the next segment names the discipline.
        "Senior Manager, Clinical Engineering & Data Analytics",
        # Role-last format: the trailing segment names the role.
        "Data Platform - Senior Product Manager",
        # Center/centre poison the word "data" itself (facilities work), so
        # they conflict anywhere in the title, qualifier or not.
        "Electrical Engineering Lead, Data Centers - Remote (U.S.)",
    ):
        assert not _title_is_in_lane(still_conflicting, q), (
            f"{still_conflicting!r} is not a data-engineering role"
        )
