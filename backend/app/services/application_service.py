from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, case, func, literal, or_
from sqlalchemy.orm import Session

# The mandatory vertical scope. Every list-level read of applications goes
# through it so quest rows never leak into career surfaces by omission.
from job_finder.models.database import APPLICATION_VERTICALS, scoped_applications
from job_finder.staffing import STAFFING_AGENCY_NAMES
from app.models.application import ApplicationRecord

# A place filter keyed to a city name alone drops every metro-sibling city:
# "Los Angeles" would hide Beverly Hills, Santa Monica, Culver City, etc.,
# which is not what a job seeker means by their city. Expand a known metro to
# its cities so on-site work anywhere in the metro still surfaces.
_METRO_CITIES: dict[str, tuple[str, ...]] = {
    "los angeles": (
        "los angeles", "beverly hills", "santa monica", "culver city", "pasadena",
        "burbank", "glendale", "long beach", "torrance", "el segundo", "marina del rey",
        "west hollywood", "hollywood", "inglewood", "hawthorne", "manhattan beach",
        "playa vista", "venice", "westwood", "century city", "sherman oaks",
        "studio city", "north hollywood", "van nuys", "woodland hills", "el monte",
        "alhambra", "monterey park", "redondo beach", "santa clarita", "universal city",
    ),
    "san francisco": (
        "san francisco", "oakland", "berkeley", "san mateo", "palo alto", "mountain view",
        "menlo park", "redwood city", "sunnyvale", "santa clara", "san jose", "cupertino",
        "emeryville", "south san francisco", "foster city", "burlingame",
    ),
    "new york": (
        "new york", "brooklyn", "manhattan", "queens", "jersey city", "hoboken",
        "long island city", "newark",
    ),
    "seattle": ("seattle", "bellevue", "redmond", "kirkland", "tacoma"),
    "boston": ("boston", "cambridge", "somerville", "waltham", "burlington"),
    "austin": ("austin", "round rock"),
    "chicago": ("chicago", "evanston"),
    "denver": ("denver", "boulder"),
    "san diego": ("san diego", "la jolla", "carlsbad"),
}


def _metro_cities_for(location: str) -> tuple[str, ...] | None:
    """The metro's city list if `location` names a known metro, else None."""
    low = " ".join((location or "").lower().split())
    for metro, cities in _METRO_CITIES.items():
        if metro in low:
            return cities
    return None

_ALLOWED_SORT_BY = frozenset({
    "overall_score", "date_found", "company", "job_title", "salary_min", "salary_max",
    "event_start", "updated_at",
    "rank",
})


def _utcnow():
    return datetime.now(timezone.utc)


def local_calendar_window_utc(
    days: int = 1,
    timezone_name: str = "UTC",
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """UTC-naive bounds for the reader's current local calendar window.

    ``date_found`` is stored as a naive UTC datetime. A label such as "new
    today" therefore needs the browser's IANA timezone translated to UTC
    before it can be compared honestly. Calendar days are intentional here:
    one day starts at local midnight, not 24 hours before the request. ZoneInfo
    also keeps the boundary correct across 23/25-hour DST days.
    """
    ref = now or _utcnow()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    width = max(1, min(int(days), 365))
    local_today = ref.astimezone(zone).date()
    start_local = datetime.combine(
        local_today - timedelta(days=width - 1),
        time.min,
        tzinfo=zone,
    )
    end_local = datetime.combine(
        local_today + timedelta(days=1),
        time.min,
        tzinfo=zone,
    )
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def found_window_condition(
    model,
    days: int = 1,
    timezone_name: str = "UTC",
    *,
    now: datetime | None = None,
):
    """Rows first seen in the reader's calendar window and not known stale.

    First-seen time is the required clock. A newly changed source date cannot
    resurrect a row Questboard already had. Conversely an undated arrival is
    kept because the source has not proved it stale. A verifiable post date
    older than seven calendar days is the one conservative exclusion retained
    from the prior freshness contract.
    """
    ref = now or _utcnow()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    current_utc = ref.astimezone(timezone.utc).replace(tzinfo=None)
    start, end = local_calendar_window_utc(days, timezone_name, now=ref)
    today_start, _ = local_calendar_window_utc(1, timezone_name, now=ref)
    stale_floor = (today_start - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    posted = func.coalesce(model.date_posted, "")
    return and_(
        model.date_found >= start,
        model.date_found < end,
        # A bad scraper clock must not manufacture an arrival that has not
        # happened yet, even when its timestamp falls later on the same local
        # calendar day.
        model.date_found <= current_utc,
        ~and_(
            posted >= "2000-01-01",
            posted < stale_floor,
            func.lower(func.coalesce(model.date_confidence, "")) != "missing",
        ),
    )


# Casting / audition quests are short-lived, and their real audition date lives
# only in the posting text (e.g. "auditions JUNE 15"), so event_start is NULL
# and the upcoming-only filter can't expire them. Once the source's publish date
# is older than this shelf life, the call has almost certainly passed. Only ISO
# date_posted strings sort below the cutoff, so free-text ("Reposted 9 days ago")
# and absent dates are conservatively KEPT on the board.
TIME_SENSITIVE_VERTICALS = ("camera",)
TIME_SENSITIVE_SHELF_DAYS = 30


def time_sensitive_stale(model, now: datetime | None = None):
    """A SQLAlchemy condition that is TRUE for a stale time-sensitive quest.

    Three prongs: any vertical whose event day (UTC) has already passed, any
    quest whose stated end/deadline day has passed, and the camera shelf life
    for casting calls that carry no event date at all.
    Negate with ``~`` to keep everything else. ``model`` is the caller's
    ApplicationRecord class (board_summary imports a different one), so the
    filter binds to that module's mapped columns.
    """
    ref = now or datetime.now(timezone.utc)
    cutoff = (ref - timedelta(days=TIME_SENSITIVE_SHELF_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    today = ref.strftime("%Y-%m-%d")
    return or_(
        # A dated event strictly before today has happened; the row leaves the
        # board whatever its vertical. SQLite stores event_start as text, so
        # go through date(), which yields the ISO day for real datetimes and
        # NULL for free text; coalesce turns that NULL into "keep", so a value
        # that cannot prove the event passed never hides a row.
        func.coalesce(func.date(model.event_start) < today, False),
        # Some quests are actionable throughout a window rather than on one
        # event day: studies use event_end for the last session and scholarships
        # use it for the application deadline.  Keep the whole stated day, then
        # hide it on the next UTC calendar day.  Free text stays conservative
        # because date() returns NULL and coalesce turns that into "keep".
        func.coalesce(func.date(model.event_end) < today, False),
        and_(
            model.vertical.in_(TIME_SENSITIVE_VERTICALS),
            model.event_start.is_(None),
            # Only a real ISO date_posted expires. The >= "2000-01-01" floor drops
            # empty strings and free text ("Reposted 9 days ago"), which sort below
            # a real year and would otherwise look "older than the cutoff".
            model.date_posted >= "2000-01-01",
            model.date_posted < cutoff,
        ),
    )


# Per-period -> annual multipliers for pay filtering. "session" is absent on
# purpose: per-gig pay is not a rate and can neither pass nor fail an annual
# scale, so those rows are treated like no-stated-pay (always kept).
_PERIOD_TO_ANNUAL = {"hourly": 2080, "daily": 260, "weekly": 52, "monthly": 12}
_SESSION_PERIOD = "session"


def _annual_pay_bounds(model):
    """Annual-scale (lo, hi) pay expressions for filtering.

    Prefer the parser's annualized columns; when they are empty (most stored
    rows carry only the raw per-period numbers) annualize the raw value at
    comparison time from salary_period. Unknown/annual periods compare as-is.
    Display never uses these: the card always shows the raw stated numbers.
    """

    def annualize(raw):
        return case(
            *(
                (func.lower(func.coalesce(model.salary_period, "")) == period, raw * mult)
                for period, mult in _PERIOD_TO_ANNUAL.items()
            ),
            else_=raw,
        )

    lo = func.coalesce(model.salary_min_annualized, annualize(model.salary_min))
    hi = func.coalesce(model.salary_max_annualized, annualize(model.salary_max))
    return lo, hi


def stated_pay_filter(
    model,
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_currency: str | None = None,
):
    """The annual pay floor/ceiling as one condition, or None when unset.

    Mirrors job_finder.pipeline._job_salary_passes: use the range midpoint
    when both ends are stated, the one stated bound otherwise, and KEEP rows
    with no salary data (dropping them would hide most listings, and "no pay
    stated" is neither "below the floor" nor "above the ceiling"). Per-gig
    "session" pay is kept without comparison, like no-stated-pay.
    A row that NAMES a different currency is kept as not-comparable:
    Questboard does not guess exchange rates. A BLANK currency compares
    numerically. 96% of scraped rows carry no currency tag, so exempting
    them turned the pay floor off almost everywhere (2026-08-13 audit: 94
    of 460 rows on a $190K+ board stated sub-floor pay). Aggregator-modeled
    bands (salary_source=source_estimate) are kept without comparison, the
    same ruling _job_salary_passes makes: an estimate is context, not
    grounds for exclusion.
    """
    if salary_min is None and salary_max is None:
        return None
    lo, hi = _annual_pay_bounds(model)

    def bounds_pass(check):
        return or_(
            and_(lo.isnot(None), hi.isnot(None), check((lo + hi) / 2)),
            and_(lo.is_(None), hi.isnot(None), check(hi)),
            and_(lo.isnot(None), hi.is_(None), check(lo)),
        )

    checks = []
    if salary_min is not None:
        checks.append(bounds_pass(lambda value: value >= salary_min))
    if salary_max is not None:
        checks.append(bounds_pass(lambda value: value <= salary_max))
    keep_without_comparison = []
    target_currency = (salary_currency or "").strip().upper()
    if target_currency:
        row_currency = func.upper(func.trim(func.coalesce(model.salary_currency, "")))
        keep_without_comparison.append(
            and_(row_currency != "", row_currency != target_currency)
        )
    return or_(
        *keep_without_comparison,
        and_(lo.is_(None), hi.is_(None)),
        func.lower(func.coalesce(model.salary_period, "")) == _SESSION_PERIOD,
        func.lower(func.trim(func.coalesce(model.salary_source, "")))
        == "source_estimate",
        and_(*checks),
    )


def stated_pay_within_ceiling(
    record,
    ceiling: float | None,
    salary_currency: str | None = None,
) -> bool:
    """Python mirror of stated_pay_filter's ceiling, for rows a service
    already fetched (the work lane's roles view orders in Python). Keep the
    two in sync: no stated pay and per-gig session pay always pass; only a
    STATED different currency skips the comparison, a blank one compares."""
    if ceiling is None:
        return True
    if (
        str(getattr(record, "salary_source", "") or "").strip().lower()
        == "source_estimate"
    ):
        return True
    target_currency = (salary_currency or "").strip().upper()
    listing_currency = str(getattr(record, "salary_currency", "") or "").strip().upper()
    if target_currency and listing_currency and listing_currency != target_currency:
        return True
    period = (getattr(record, "salary_period", "") or "").lower()
    if period == _SESSION_PERIOD:
        return True
    mult = _PERIOD_TO_ANNUAL.get(period, 1)

    def annual(annualized, raw):
        if annualized is not None:
            return annualized
        return raw * mult if raw is not None else None

    lo = annual(getattr(record, "salary_min_annualized", None), record.salary_min)
    hi = annual(getattr(record, "salary_max_annualized", None), record.salary_max)
    if lo is None and hi is None:
        return True
    if lo is not None and hi is not None:
        return (lo + hi) / 2 <= ceiling
    return (hi if hi is not None else lo) <= ceiling


def _word_padded_location(model):
    """The location text with common list delimiters flattened to spaces and
    a space at each end, so ' XX ' patterns match on word boundaries: "OR/WA
    only" carries " WA ", "San Diego, CA" carries " CA ", and Casablanca
    never does. Dots collapse first so "D.C." reads as one DC token."""
    text = func.replace(model.location, ".", "")
    for delimiter in (",", "(", ")", "/", "&", ";", "-"):
        text = func.replace(text, delimiter, " ")
    return literal(" ") + text + literal(" ")


# The country-level US names a nationwide posting carries when it names no
# city. Matched as a whole location or as a trailing segment of a multi-place
# list, never as a substring, so "New York, United States" stays a NY role.
_US_COUNTRY_TERMS = (
    "united states of america",
    "united states",
    "u.s.a.",
    "u.s.",
    "usa",
    "us",
)


def _looks_like_us_place(location: str) -> bool:
    """True when the seeker's own typed place is a US country term."""
    return location.strip().lower().rstrip(".") in {t.rstrip(".") for t in _US_COUNTRY_TERMS}


def _nationwide_us_match(model):
    """SQL for a location that is nationwide US: a US country term is a full
    ';'-separated segment anywhere in the location, not only the whole string
    or the trailing option. "United States; Canada" and "Canada; United
    States; Mexico" both count; "New York, United States" (comma, not a
    segment boundary) does not."""
    # Collapse the spaces around every ';' so a segment is delimited the same
    # way regardless of "; " / " ;" / ";", then wrap in ';' so the first and
    # last segments have a boundary on both sides too.
    lowered = func.lower(func.trim(model.location))
    collapsed = func.replace(func.replace(lowered, "; ", ";"), " ;", ";")
    padded = literal(";") + collapsed + literal(";")
    return or_(*[padded.like(f"%;{term};%") for term in _US_COUNTRY_TERMS])


def place_filter(model, location: str | None, location_strict: bool = False):
    """The board's reachability filter as one condition, or None when unset.

    A place filter narrows to quests you can actually reach; it must never
    hide work-from-anywhere. Rows pass when their location matches, when
    they say remote/online/nationwide in any wording, or when the source
    stated no place at all (unknown is not "elsewhere"). A typed US state
    (either spelling) matches the pre-parsed state_codes token field, so
    "Georgia" and "GA" both find a "VA, GA & NC only" bonus and neither
    matches "Guadalajara" or "West Virginia" (job_finder.us_states explains
    why this beats tokenizing prose in SQL). state_codes is only populated
    on rows saved since the parser shipped, so a state ALSO matches the raw
    location text: the spelled-out name on a leading word boundary (minus
    any longer state name that contains it, so Virginia still never leaks
    West Virginia), and the UPPERCASE abbreviation as a whole word
    (case-sensitive, so prose "in" is never Indiana). A typed city or free
    text keeps a plain location substring match.
    """
    if not location:
        return None
    from job_finder.us_states import STATE_TO_ABBR, state_aliases

    metro = _metro_cities_for(location)
    aliases = state_aliases(location)
    # A US city or state means US-nationwide postings ("United States" with no
    # city) are reachable for this seeker.
    seeker_is_us = bool(metro or aliases) or _looks_like_us_place(location)
    if metro:
        # "Los Angeles" also finds Beverly Hills / Santa Monica / etc. — the
        # seeker means the metro, not only rows that name the core city.
        place_match = or_(*[model.location.ilike(f"%{c}%") for c in metro])
    elif aliases:
        full_name, abbr = aliases
        token_match = model.state_codes.like(f"%,{abbr},%")
        padded = _word_padded_location(model)
        name_match = padded.ilike(f"% {full_name}%")
        longer_names = [
            name for name in STATE_TO_ABBR if name != full_name and full_name in name
        ]
        if longer_names:
            name_match = and_(
                name_match,
                *(~func.lower(model.location).like(f"%{name}%") for name in longer_names),
            )
        # length-vs-replace is the portable case-sensitive containment test:
        # SQLite LIKE ignores ASCII case, replace() never does.
        abbr_match = func.length(padded) != func.length(
            func.replace(padded, f" {abbr} ", "")
        )
        place_match = or_(token_match, name_match, abbr_match)
    else:
        place_match = model.location.ilike(f"%{location.strip()}%")
    if location_strict:
        # "near me only": keep only rows that actually match the place, so
        # the filter visibly bites. Remote and placeless supply drop.
        return place_match
    # Remote passes only when it is remote FOR YOU: a row whose stated
    # scope names another country ("Remote, India", "Remote (UK Based
    # only)") is not reachable from a US place and must earn its spot
    # through the place match instead. Unstated scope ('' / NULL) stays
    # conservatively kept.
    not_intl_only = or_(
        model.remote_scope.is_(None),
        model.remote_scope != "intl",
    )
    remote_ish = or_(
        model.location.ilike("%remote%"),
        model.location.ilike("%online%"),
        model.location.ilike("%nationwide%"),
        model.location.ilike("%anywhere%"),
        model.is_remote.is_(True),
    )
    reachable = [
        place_match,
        model.location.is_(None),
        model.location == "",
        and_(remote_ish, not_intl_only),
    ]
    # A bare country ("United States", "USA") is a nationwide posting: reachable
    # from any US place. Gated on a US seeker so a non-US city never inherits it,
    # and matched as a whole segment so "New York, United States" (a specific NY
    # role) is not swept in, while "...; United States" (a nationwide option in a
    # multi-location list) is.
    if seeker_is_us:
        reachable.append(_nationwide_us_match(model))
    return or_(*reachable)


def founding_role_condition(model):
    """The single, narrow definition of a founding seat used by every shelf.

    Company-origin prose often mentions a founding team without making the
    advertised role one. These phrases describe the seat itself; keeping the
    predicate here prevents Founding and Startup from quietly disagreeing.
    """
    title = func.lower(func.coalesce(model.job_title, ""))
    description = func.lower(func.coalesce(model.description, ""))
    explicit_founding_phrases = (
        "join our founding team",
        "join the founding team",
        "part of our founding team",
        "part of the founding team",
        "member of our founding team",
        "member of the founding team",
        "as a founding team member",
        "first data hire",
        "first dedicated data hire",
        "first data engineer",
        "first analytics hire",
        "first dedicated analytics hire",
        "first analytics engineer",
        "first engineering hire",
        "first product hire",
        "first design hire",
        "first marketing hire",
        "first sales hire",
        "first finance hire",
    )
    return or_(
        title.like("%founding%"),
        *(description.like(f"%{phrase}%") for phrase in explicit_founding_phrases),
    )


def board_filter_conditions(
    model,
    *,
    search: str | None = None,
    location: str | None = None,
    location_strict: bool = False,
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_currency: str | None = None,
    is_remote: bool | None = None,
    founding_only: bool = False,
    exclude_staffing_agencies: bool = False,
    first_quest_ok: bool | None = None,
    posted_within_days: int | None = None,
    found_within_days: int | None = None,
    timezone_name: str = "UTC",
) -> list:
    """The user-set board filters as reusable SQLAlchemy conditions.

    One vocabulary for every surface: the /applications list, the
    /board/summary rail counts, and the work lane's category badges all
    build from here, so a filtered board and its counts cannot disagree.
    ``model`` is the caller's ApplicationRecord class, like
    time_sensitive_stale.
    """
    conditions: list = []
    if is_remote is not None:
        conditions.append(model.is_remote == is_remote)
    if founding_only:
        conditions.append(founding_role_condition(model))
    if exclude_staffing_agencies:
        company = func.lower(func.coalesce(model.company, ""))
        conditions.append(and_(
            *(~company.like(f"%{name}%") for name in STAFFING_AGENCY_NAMES)
        ))
    place = place_filter(model, location, location_strict)
    if place is not None:
        conditions.append(place)
    pay = stated_pay_filter(model, salary_min, salary_max, salary_currency)
    if pay is not None:
        conditions.append(pay)
    if first_quest_ok is not None:
        # "No experience needed", provably. Only rows whose source stated a
        # beginner-friendly signal carry the flag; career rows and unmarked
        # quest rows never have it, so they drop rather than get guessed in.
        if first_quest_ok:
            conditions.append(model.first_quest_ok.is_(True))
        else:
            conditions.append(
                or_(
                    model.first_quest_ok.is_(False),
                    model.first_quest_ok.is_(None),
                )
            )
    if posted_within_days is not None:
        # "Posted in the last N days", provably. date_posted is a raw source
        # string, ISO-8601 when the source stated a real date and free text
        # ("Reposted 9 Days Ago") when it did not. Only rows whose stored
        # value sorts inside [now - N days, now + 1 day] count; ISO strings
        # compare correctly as text, and the future-bounded upper edge drops
        # every non-ISO value (letters and bare day counts sort above it).
        # A date-only string from yesterday cannot prove it is inside a
        # 24-hour window, so it does not count: undercounting is the honest
        # side of that ambiguity. Rows the classifier marked "missing" never
        # count even if a string survives.
        now = datetime.now(timezone.utc)
        lower = (now - timedelta(days=posted_within_days)).strftime("%Y-%m-%dT%H:%M:%S")
        upper = now.strftime("%Y-%m-%dT%H:%M:%S")
        conditions.append(model.date_posted >= lower)
        conditions.append(model.date_posted <= upper)
        conditions.append(
            func.lower(func.coalesce(model.date_confidence, "")) != "missing"
        )
    if isinstance(found_within_days, int):
        # "New today" is a calendar promise in the reader's timezone, using
        # Questboard's first-seen clock. It is not a rolling 24-hour window,
        # and a source changing its posted date cannot make an existing row
        # newly found. Unknown source dates still pass; only a verifiably stale
        # post is excluded.
        conditions.append(
            found_window_condition(
                model,
                found_within_days,
                timezone_name,
            )
        )
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                model.job_title.ilike(pattern),
                model.company.ilike(pattern),
                model.description.ilike(pattern),
                # a typed city must find the sit whose location says it
                model.location.ilike(pattern),
            )
        )
    return conditions


def source_category_condition(model, source_category: str):
    """Build the browse predicate for a source/category shelf.

    Most shelves remain provenance-based. Crypto is an industry identity and
    Startup is an employer/seat identity, so both work across ATS, remote
    boards, and aggregators. Source fallbacks keep older pre-taxonomy rows
    visible without treating a broad board itself as proof of startup status.
    """
    from job_finder.tools.scrapers import get_registry

    wanted = {
        name.lower()
        for name, meta in get_registry().items()
        if getattr(meta, "category", "") == source_category
    }
    source_predicate = (
        func.lower(model.source).in_(wanted)
        if wanted
        else func.lower(model.source) == "\x00__none__"
    )
    if source_category == "crypto":
        taxonomy_predicate = func.lower(
            func.coalesce(model.industry_tags, "[]")
        ).like('%"crypto"%')
        return or_(taxonomy_predicate, source_predicate)
    if source_category == "startup":
        # Strict, auditable signals only. In particular, an Ashby/Greenhouse/
        # BuiltIn row is not a startup merely because startups use that board.
        company_type = func.lower(func.coalesce(model.company_type, ""))
        funding_stage = func.lower(func.coalesce(model.funding_stage, ""))
        early_funding = or_(
            funding_stage.like("%pre-seed%"),
            funding_stage.like("%pre seed%"),
            funding_stage.like("%seed%"),
            funding_stage.like("%angel%"),
            funding_stage.like("%bootstrap%"),
            funding_stage.like("%series a%"),
        )
        return or_(
            source_predicate,
            company_type == "early startup",
            early_funding,
            founding_role_condition(model),
        )
    return source_predicate


def publishable_source_condition(model):
    """Exclude sources explicitly registered as research, never content.

    This is a read-time backstop for databases created before a source was
    demoted. Refresh selection already refuses these sources; applying the
    same contract here prevents their legacy rows from masquerading as live
    opportunities before the versioned cleanup has run.
    """
    from job_finder.tools.scrapers import get_registry

    research_only = {
        name.lower()
        for name, meta in get_registry().items()
        if getattr(meta, "research_only", False)
    }
    if not research_only:
        return model.id.isnot(None)
    return ~func.lower(func.coalesce(model.source, "")).in_(research_only)


def get_applications(
    db: Session,
    *,
    status: str | None = None,
    min_score: float | None = None,
    recommendation: str | None = None,
    score_source: str | None = None,
    source: str | None = None,
    source_category: str | None = None,
    search: str | None = None,
    title_token_groups: list[list[str]] | None = None,
    company_type: str | None = None,
    is_remote: bool | None = None,
    founding_only: bool = False,
    exclude_staffing_agencies: bool = False,
    work_type: str | None = None,
    location: str | None = None,
    location_strict: bool = False,
    facet: str | None = None,
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_currency: str | None = None,
    profile: str | None = None,
    workspace_id: str | None = None,
    shared_quest_workspace: str | None = None,
    search_run_id: str | None = None,
    first_seen_run_id: str | None = None,
    exclude_dead: bool = False,
    upcoming_only: bool = False,
    first_quest_ok: bool | None = None,
    posted_within_days: int | None = None,
    found_within_days: int | None = None,
    timezone_name: str = "UTC",
    event_within_days: int | None = None,
    sort_by: str = "overall_score",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 25,
    verticals: list[str] | None = None,
) -> tuple[list[ApplicationRecord], int]:
    if sort_by not in _ALLOWED_SORT_BY:
        sort_by = "overall_score"
    # Career by default: the classic page and its counts never see quest rows
    # (which are unscored and would float to the top of the default
    # overall_score desc nullsfirst sort) unless a caller opts in.
    query = scoped_applications(db.query(ApplicationRecord), verticals)
    query = query.filter(publishable_source_condition(ApplicationRecord))

    if status:
        # Single value or comma list, mirroring the vertical param: the log
        # reads its whole spread (clipped, applied, shelved, done...) in one
        # query so every surface shares one cache entry.
        wanted_statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(wanted_statuses) == 1:
            query = query.filter(ApplicationRecord.status == wanted_statuses[0])
        elif wanted_statuses:
            query = query.filter(ApplicationRecord.status.in_(wanted_statuses))
    if min_score is not None:
        query = query.filter(ApplicationRecord.overall_score >= min_score)
    if recommendation:
        query = query.filter(ApplicationRecord.recommendation == recommendation)
    if score_source:
        query = query.filter(ApplicationRecord.score_source == score_source)
    if source:
        query = query.filter(ApplicationRecord.source == source)
    if source_category:
        query = query.filter(
            source_category_condition(ApplicationRecord, source_category)
        )
    if company_type:
        query = query.filter(ApplicationRecord.company_type == company_type)
    if work_type:
        query = query.filter(ApplicationRecord.work_type == work_type)
    # The user-set board filters (place, pay, remote, search, freshness,
    # no-experience) come from the shared builder so /board/summary and the
    # work lane's badges apply the exact same predicates.
    for condition in board_filter_conditions(
        ApplicationRecord,
        search=search,
        location=location,
        location_strict=location_strict,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        is_remote=is_remote,
        founding_only=founding_only,
        exclude_staffing_agencies=exclude_staffing_agencies,
        first_quest_ok=first_quest_ok,
        posted_within_days=posted_within_days,
        found_within_days=found_within_days,
        timezone_name=timezone_name,
    ):
        query = query.filter(condition)
    if facet:
        # A facet is a kind's own sub-shelf (packages/kinds/kinds.json):
        # rows pass when any of its terms appears in the title or the
        # description. Resolved against the requested verticals, so "pets"
        # means something on the lookafter lane and 400s anywhere else.
        from job_finder.kinds import facet_for

        resolved = next(
            (f for f in (facet_for(v, facet) for v in verticals or ()) if f is not None),
            None,
        )
        if resolved is None:
            raise ValueError(f"unknown facet {facet!r} for the requested verticals")
        # Leading word boundary: match against ' '||field with a '% term%'
        # pattern, so 'cat' finds "cat sitting" and "my cats" but never
        # 'vacation', and 'pet' never matches 'carpet'. Suffix stays open on
        # purpose (plurals and compounds like 'catsitter' should match).
        padded_title = " " + func.lower(ApplicationRecord.job_title)
        padded_desc = " " + func.lower(ApplicationRecord.description)
        query = query.filter(
            or_(
                *(
                    clause
                    for term in resolved.terms
                    for clause in (
                        padded_title.like(f"% {term.lower()}%"),
                        padded_desc.like(f"% {term.lower()}%"),
                    )
                )
            )
        )
    if shared_quest_workspace:
        # hosted board read: your rows plus the shared quest pool
        # (see app.services.row_scope for the visibility contract)
        from app.services.row_scope import visible_rows_filter

        query = query.filter(visible_rows_filter(shared_quest_workspace))
    elif workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    elif profile:
        query = query.filter(ApplicationRecord.profile == profile)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    if first_seen_run_id:
        query = query.filter(ApplicationRecord.first_seen_run_id == first_seen_run_id)
    if exclude_dead:
        # Hide only CONFIRMED-dead postings; unknown/alive/never-checked stay.
        # expired rows (source stopped listing them) hide with the dead ones;
        # include_dead=true still surfaces both tombstone shapes
        query = query.filter(ApplicationRecord.url_status.notin_(("dead", "expired")))
    if upcoming_only:
        # Drop quests whose taping/session already happened. NULL event_start
        # (career rows, rolling signups) always passes: "no date" is not
        # "in the past". Stored values are naive UTC, so compare naive UTC.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = query.filter(
            or_(
                ApplicationRecord.event_start.is_(None),
                ApplicationRecord.event_start >= now,
            )
        )
        # Casting calls carry their date only in the text, so also drop the
        # ones whose publish date is past the shelf life.
        query = query.filter(~time_sensitive_stale(ApplicationRecord))
    if event_within_days is not None:
        # Rows whose taping/session date falls inside the next N days. Only
        # real event_start values count; rows with no event date are not
        # "happening this week". Stored values are naive UTC.
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        query = query.filter(
            ApplicationRecord.event_start.isnot(None),
            ApplicationRecord.event_start >= now_naive,
            ApplicationRecord.event_start <= now_naive + timedelta(days=event_within_days),
        )
    if title_token_groups:
        # Role-family retrieval is order-independent: "Manager, Data
        # Engineering" must answer the saved role "Data Engineering
        # Manager". Callers still apply an exact token check after retrieval;
        # these SQL predicates keep the candidate pool bounded and indexed
        # filters (location, freshness, status) ahead of that check.
        variants = {
            "architect": ("architect", "architecture"),
            "engineer": ("engineer", "engineering"),
            "manager": ("manager", "mgr"),
            "ops": ("ops", "operations"),
            # the role-token alias maps scientist/scientists -> "science", which
            # is NOT a substring of the words in real titles, so expand it back
            # to the surface forms or every Scientist row is dropped here.
            "science": ("science", "scientist", "scientists"),
            "senior": ("senior", "sr"),
            "steward": ("steward", "stewardship"),
        }
        lowered_title = func.lower(ApplicationRecord.job_title)
        role_groups = []
        for raw_group in title_token_groups[:20]:
            tokens = [
                token.lower()
                for token in raw_group[:12]
                if token and token.isalnum()
            ]
            if not tokens:
                continue
            role_groups.append(
                and_(
                    *(
                        or_(
                            *(
                                lowered_title.like(f"%{variant}%")
                                for variant in variants.get(token, (token,))
                            )
                        )
                        for token in tokens
                    )
                )
            )
        if role_groups:
            query = query.filter(or_(*role_groups))

    total = query.count()

    # Sorting
    if sort_by == "rank":
        bucket_order = case(
            (ApplicationRecord.match_bucket == "primary", 0),
            (ApplicationRecord.match_bucket == "adjacent", 1),
            else_=2,
        )
        direction = ApplicationRecord.rank_score.asc().nullslast() if sort_dir == "asc" else ApplicationRecord.rank_score.desc().nullslast()
        query = query.order_by(bucket_order.asc(), direction, ApplicationRecord.date_found.desc())
    else:
        sort_col = getattr(ApplicationRecord, sort_by, ApplicationRecord.overall_score)
        if sort_dir == "asc":
            query = query.order_by(sort_col.asc().nullslast())
        else:
            query = query.order_by(sort_col.desc().nullsfirst())

    # Pagination
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()

    return items, total


def live_rows_by_source(db: Session) -> dict[str, int]:
    """How many rows each source currently keeps on the board, keyed lowercase.

    The run log answers "did this source work". It cannot answer "is this
    source worth its time to me", because whether a found job survives is
    entirely about one person's roles, place, and pay. On one real board
    Workday found 266 jobs and 4 survived, while Himalayas found 59 and kept
    444 across runs. Neither number means Workday is broken; it means Workday
    suits a different search. Pairing the two is what lets a person judge
    their own sources instead of inheriting someone else's verdict.

    Dead and expired rows stay out, matching what the board counts.
    """
    from sqlalchemy import func

    rows = (
        db.query(ApplicationRecord.source, func.count(ApplicationRecord.id))
        .filter(ApplicationRecord.vertical.in_(("career", "work")))
        .filter(ApplicationRecord.url_status.notin_(("dead", "expired")))
        .group_by(ApplicationRecord.source)
        .all()
    )
    counts: dict[str, int] = {}
    for source, count in rows:
        key = (source or "").strip().lower()
        if key:
            counts[key] = counts.get(key, 0) + count
    return counts


def get_application(db: Session, app_id: int, workspace_id: str | None = None) -> ApplicationRecord | None:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        # yours, or a read of a shared quest row (the hosted board is one
        # felt for everyone; mutations clone first, reads need not)
        from sqlalchemy import and_, or_

        query = query.filter(
            or_(
                ApplicationRecord.workspace_id == workspace_id,
                and_(
                    ApplicationRecord.workspace_id.is_(None),
                    ApplicationRecord.vertical != "career",
                ),
            )
        )
    return query.first()


def create_application(db: Session, data, workspace_id: str | None = None) -> ApplicationRecord:
    """Create a new application record from an ApplicationCreate schema."""
    vertical = data.vertical or "career"
    if vertical not in APPLICATION_VERTICALS:
        raise ValueError(f"unknown application vertical: {vertical!r}")
    record = ApplicationRecord(
        job_title=data.job_title,
        company=data.company,
        location=data.location,
        # Empty URLs store as NULL so the unique constraint permits many
        # URL-less rows (personal quests have no source link), matching
        # job_finder save_application's convention.
        job_url=data.job_url or None,
        source=data.source,
        description=data.description,
        is_remote=data.is_remote,
        salary_min=data.salary_min,
        salary_max=data.salary_max,
        status=data.status,
        notes=data.notes,
        profile=data.profile,
        vertical=vertical,
        workspace_id=workspace_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _clone_shared_quest_row(
    db: Session, shared: ApplicationRecord, workspace_id: str
) -> ApplicationRecord:
    """Copy a shared quest row into a workspace (hosted clone-on-touch).

    The shared row stays pristine for everyone else; the copy is the
    user's, and board reads hide the original behind it (job_url dedupe).
    """
    values = {
        column.name: getattr(shared, column.name)
        for column in ApplicationRecord.__table__.columns
        if column.name != "id"
    }
    values["workspace_id"] = workspace_id
    copy = ApplicationRecord(**values)
    db.add(copy)
    db.flush()
    return copy


def update_application(
    db: Session,
    app_id: int,
    workspace_id: str | None = None,
    allow_quest_clone: bool = False,
    **kwargs,
) -> ApplicationRecord | None:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    record = query.first()
    if not record and workspace_id and allow_quest_clone:
        # hosted: the id may name a SHARED quest row; touch = clone first.
        # A stale client can send the shared id after a copy already
        # exists, so resolve to the existing copy by URL before cloning.
        from app.services.row_scope import shared_quest_row_filter

        shared = db.query(ApplicationRecord).filter(shared_quest_row_filter(app_id)).first()
        if shared is not None:
            record = (
                db.query(ApplicationRecord)
                .filter(
                    ApplicationRecord.workspace_id == workspace_id,
                    ApplicationRecord.job_url == shared.job_url,
                )
                .first()
            ) or _clone_shared_quest_row(db, shared, workspace_id)
    if not record:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(record, key):
            setattr(record, key, value)
    record.updated_at = _utcnow()
    if kwargs.get("status") == "applied" and not record.date_applied:
        record.date_applied = _utcnow()
    db.commit()
    db.refresh(record)
    return record


def check_urls(
    db: Session,
    ids: list[int] | None = None,
    limit: int = 100,
    workspace_id: str | None = None,
    live_only: bool = False,
    search_run_id: str | None = None,
) -> dict:
    """Verify job URLs and update ``url_status``. Returns summary counts.

    ``live_only`` skips rows already off the board (dead/expired), so the
    scheduler's rolling re-verification never wastes its batch re-proving
    what is already tombstoned. A plain HTTP 200 is not enough evidence:
    several aggregators keep the article after its external application has
    expired, and some ATSes redirect a removed ``/jobs/<id>`` URL to the
    company's job index with ``?error=true``.
    """
    import requests as req
    from threading import Lock
    from urllib.parse import parse_qs, quote, unquote, urlparse

    query = db.query(ApplicationRecord).filter(ApplicationRecord.job_url.isnot(None))
    if live_only:
        query = query.filter(ApplicationRecord.url_status.notin_(("dead", "expired")))
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    if search_run_id:
        query = query.filter(ApplicationRecord.search_run_id == search_run_id)
    if ids:
        query = query.filter(ApplicationRecord.id.in_(ids))
    else:
        # Check oldest-checked first, or never-checked
        query = query.order_by(ApplicationRecord.last_checked_at.asc().nullsfirst())
    records = query.limit(limit).all()

    # Classify ONE url. Only high-confidence evidence means the posting is
    # gone: 404/410, a source-specific dead redirect, or explicit closed-page
    # prose. Bot blocks and transport errors remain unknown.
    # 403/405/429/5xx are usually bot-blocks or HEAD-not-supported, and
    # timeouts/connection errors are transient, none of those should mark a
    # live job dead (that would hide good postings). Those map to "unknown".
    soft_dead_phrases = (
        "job is no longer available",
        "job posting is no longer available",
        "position is no longer available",
        "job you are looking for is no longer open",
        "job posting has expired",
        "this job has expired",
        "position has been filled",
        "opportunity is no longer available",
        "no longer accepting applications",
        "this job is closed",
        "this position has been closed",
        "this vacancy is no longer available",
        "the job is no longer open",
        "the job you requested was not found",
    )
    content_check_hosts = (
        "ashbyhq.com",
        "greenhouse.io",
        "lever.co",
        "myworkdayjobs.com",
        "smartrecruiters.com",
        # Web3.career deliberately keeps closed listing pages at HTTP 200 and
        # renders an explicit "This job is closed" banner. A HEAD-only check
        # therefore mistakes expired crypto roles for live opportunities.
        "web3.career",
        "workable.com",
    )
    request_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    ashby_board_cache: dict[str, tuple[str, frozenset[str]]] = {}
    ashby_board_locks: dict[str, Lock] = {}
    ashby_cache_lock = Lock()
    greenhouse_title_cache: dict[str, tuple[str, frozenset[str]]] = {}
    greenhouse_title_locks: dict[str, Lock] = {}
    greenhouse_cache_lock = Lock()

    def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
        return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)

    def _dead_redirect(requested_url: str, response) -> bool:
        final_url = str(getattr(response, "url", "") or requested_url)
        requested = urlparse(requested_url)
        final = urlparse(final_url)
        query_values = {
            key.casefold(): [str(value).casefold() for value in values]
            for key, values in parse_qs(final.query).items()
        }
        if "true" in query_values.get("error", []):
            return True
        requested_host = (requested.hostname or "").casefold()
        final_host = (final.hostname or "").casefold()
        if (
            _host_matches(requested_host, ("greenhouse.io",))
            and _host_matches(final_host, ("greenhouse.io",))
            and "/jobs/" in requested.path.casefold()
            and "/jobs/" not in final.path.casefold()
        ):
            return True
        return False

    def _get_page_status(url: str) -> str:
        """Read only the beginning of a page, enough for closed-job banners."""
        try:
            headers = {**request_headers, "Range": "bytes=0-262143"}
            with req.get(
                url,
                headers=headers,
                timeout=8,
                allow_redirects=True,
                stream=True,
            ) as response:
                if response.status_code in (404, 410):
                    return "dead"
                if response.status_code >= 400:
                    return "unknown"
                if _dead_redirect(url, response):
                    return "dead"
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_content(16_384, decode_unicode=False):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= 262_144:
                        break
                page = b"".join(chunks).decode("utf-8", "ignore").casefold()
                if any(phrase in page for phrase in soft_dead_phrases):
                    return "dead"
                return "alive"
        except Exception:
            return "unknown"

    def _classify_url(url: str, *, inspect_content: bool = False) -> str:
        try:
            r = req.head(
                url,
                timeout=8,
                allow_redirects=True,
            )
            code = r.status_code
            if code in (404, 410):
                return "dead"
            if code < 400 and _dead_redirect(url, r):
                return "dead"
            if code < 400:
                host = (urlparse(url).hostname or "").casefold()
                if inspect_content or _host_matches(host, content_check_hosts):
                    body_status = _get_page_status(url)
                    # A blocked GET does not refute a successful HEAD.
                    return "alive" if body_status == "unknown" else body_status
                return "alive"
            return "unknown"
        except Exception:
            return "unknown"

    def _ashby_board_jobs(slug: str) -> tuple[str, frozenset[str]]:
        """Return a cached snapshot of one Ashby company's live job IDs.

        Ashby's public posting pages are JavaScript shells that stay HTTP 200
        after a job disappears. Its job-board API is the authoritative live
        set. Per-slug locks prevent a refresh with several jobs from downloading
        the same (sometimes large) board response more than once.
        """
        with ashby_cache_lock:
            board_lock = ashby_board_locks.setdefault(slug, Lock())
        with board_lock:
            with ashby_cache_lock:
                cached = ashby_board_cache.get(slug)
            if cached is not None:
                return cached
            try:
                response = req.get(
                    "https://api.ashbyhq.com/posting-api/job-board/"
                    f"{quote(slug, safe='')}?includeCompensation=false",
                    headers={**request_headers, "Accept": "application/json"},
                    timeout=8,
                )
                if response.status_code in (404, 410):
                    result = ("dead", frozenset())
                elif response.status_code >= 400:
                    result = ("unknown", frozenset())
                else:
                    payload = response.json()
                    jobs = payload.get("jobs") if isinstance(payload, dict) else None
                    if not isinstance(jobs, list):
                        result = ("unknown", frozenset())
                    else:
                        live_ids = frozenset(
                            str(job.get("id") or "").strip().casefold()
                            for job in jobs
                            if isinstance(job, dict) and job.get("id")
                        )
                        result = ("alive", live_ids)
            except Exception:
                result = ("unknown", frozenset())
            with ashby_cache_lock:
                ashby_board_cache[slug] = result
            return result

    def _classify_ashby(url: str) -> str | None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        parts = [unquote(part).strip() for part in parsed.path.split("/") if part]
        if not _host_matches(host, ("ashbyhq.com",)) or len(parts) < 2:
            return None
        slug, job_id = parts[0].casefold(), parts[1].casefold()
        board_status, live_ids = _ashby_board_jobs(slug)
        if board_status != "alive":
            return board_status
        return "alive" if job_id in live_ids else "dead"

    def _title_key(value: str) -> str:
        """Stable comparison key for an aggregator title vs an ATS title."""
        words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
        aliases = {"sr": "senior", "jr": "junior", "mgr": "manager"}
        return "".join(aliases.get(word, word) for word in words)

    def _greenhouse_board_titles(slug: str) -> tuple[str, frozenset[str]]:
        """Authoritative current title set for one known Greenhouse company."""
        with greenhouse_cache_lock:
            board_lock = greenhouse_title_locks.setdefault(slug, Lock())
        with board_lock:
            with greenhouse_cache_lock:
                cached = greenhouse_title_cache.get(slug)
            if cached is not None:
                return cached
            try:
                response = req.get(
                    "https://boards-api.greenhouse.io/v1/boards/"
                    f"{quote(slug, safe='')}/jobs",
                    headers={**request_headers, "Accept": "application/json"},
                    timeout=8,
                )
                if response.status_code in (404, 410):
                    result = ("dead", frozenset())
                elif response.status_code >= 400:
                    result = ("unknown", frozenset())
                else:
                    payload = response.json()
                    jobs = payload.get("jobs") if isinstance(payload, dict) else None
                    if not isinstance(jobs, list):
                        result = ("unknown", frozenset())
                    else:
                        result = (
                            "alive",
                            frozenset(
                                _title_key(str(job.get("title") or ""))
                                for job in jobs
                                if isinstance(job, dict) and job.get("title")
                            ),
                        )
            except Exception:
                result = ("unknown", frozenset())
            with greenhouse_cache_lock:
                greenhouse_title_cache[slug] = result
            return result

    def _classify_known_greenhouse_duplicate(record: ApplicationRecord) -> str | None:
        """Cross-check aggregator copies against a known employer board.

        Aggregators can preserve a 200 page for weeks after the employer has
        removed the role. For cataloged Greenhouse companies, current board
        membership is stronger evidence than the aggregator shell. A missing
        exact title tombstones only the stale copy; blocked board requests are
        inconclusive and never hide anything.
        """
        aggregator_sources = {
            "arbeitnow", "builtin", "glassdoor", "google", "himalayas",
            "indeed", "linkedin", "remoteok", "remotive", "themuse",
            "weworkremotely", "zip_recruiter",
        }
        if (record.source or "").strip().casefold() not in aggregator_sources:
            return None
        try:
            from job_finder.config.company_catalog import lookup_company

            company = lookup_company(str(record.company or ""))
        except Exception:
            company = None
        if not company or company.get("ats") != "greenhouse" or not company.get("slug"):
            return None
        board_status, live_titles = _greenhouse_board_titles(str(company["slug"]))
        if board_status != "alive":
            return None if board_status == "unknown" else board_status
        title = _title_key(str(record.job_title or ""))
        return "alive" if title and title in live_titles else "dead"

    def _classify(record: ApplicationRecord) -> str:
        url = str(record.job_url or "")
        if (record.source or "").strip().casefold() == "ashby":
            ashby_status = _classify_ashby(url)
            if ashby_status is not None:
                return ashby_status
        primary = _classify_url(url)
        if primary == "dead":
            return primary
        # BuiltIn preserves its editorial page after the employer removes the
        # actual application. Verify the page's external Apply target; this is
        # the exact failure a person encounters after clicking through.
        if (record.source or "").strip().casefold() == "builtin":
            try:
                from job_finder.tools.scrapers.builtin import fetch_builtin_detail

                direct_url = str(
                    fetch_builtin_detail(url).get("direct_application_url") or ""
                ).strip()
            except Exception:
                direct_url = ""
            if direct_url and direct_url != url:
                direct = _classify_url(direct_url, inspect_content=True)
                if direct == "dead":
                    return "dead"
                if direct == "unknown":
                    return "unknown"
        official_duplicate = _classify_known_greenhouse_duplicate(record)
        if official_duplicate is not None:
            return official_duplicate
        return primary

    now = _utcnow()
    statuses: dict[int, str] = {}
    if records:
        from concurrent.futures import ThreadPoolExecutor
        # Posting URLs span many independent company/ATS hosts. A wider pool
        # shortens this final verification stage without changing which URLs
        # are checked or how any response is classified.
        with ThreadPoolExecutor(max_workers=min(len(records), 16)) as pool:
            for rec, status in zip(records, pool.map(_classify, records)):
                statuses[rec.id] = status

    alive = dead = unknown = 0
    for rec in records:
        status = statuses.get(rec.id, "unknown")
        rec.url_status = status
        rec.last_checked_at = now
        if status == "alive":
            alive += 1
        elif status == "dead":
            dead += 1
        else:
            unknown += 1

    db.commit()
    return {"checked": len(records), "alive": alive, "dead": dead, "unknown": unknown}


def delete_application(db: Session, app_id: int, workspace_id: str | None = None) -> bool:
    query = db.query(ApplicationRecord).filter(ApplicationRecord.id == app_id)
    if workspace_id:
        query = query.filter(ApplicationRecord.workspace_id == workspace_id)
    record = query.first()
    if not record:
        return False
    db.delete(record)
    db.commit()
    return True
