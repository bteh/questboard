"""Golden edge-case corpus for the exclusion tracer.

Every tricky filter case from this session, frozen as a regression fixture.
Each entry states a row, a filter set, a lane, and the expected verdict, so
``trace_exclusion`` on that row must name exactly that stage (or report the row
visible). The tracer runs the REAL production predicates, so these lock the
observed behavior in place: if a filter's meaning ever drifts, the matching
case flips and the test fails.

A row's ``date_found_days_ago`` (when present) is converted to a concrete
timestamp at seed time, so freshness cases stay stable regardless of the day
the suite runs. ``lanes`` lists which lanes the case is meaningful on: place,
dead-link and first-quest cases apply to both career/work and side quests;
salary, title, anchored-freshness and dedup cases are career/work only.

Verdict shape:
    {"outcome": "visible"} or {"outcome": "hidden", "stage": "<stage name>"}
"""

from __future__ import annotations

# Role families used by the career/work title-match and dedup stages.
DATA_ENGINEER_ROLES = ["Staff Data Engineer", "Data Engineer"]

# Filter presets. Copied (not shared) per case by the seeder.
_LA_SEEKER = {
    "location": "Los Angeles",
    "location_strict": False,
    "salary_min": None,
    "salary_max": None,
    "is_remote": None,
    "first_quest_ok": None,
    "posted_within_days": 30,
    "freshness_explicit": False,
    "roles": DATA_ENGINEER_ROLES,
}


def _f(**overrides):
    base = dict(_LA_SEEKER)
    base.update(overrides)
    return base


# Each case: id, label, row (ApplicationRecord field dict), filters, lane,
# expected verdict, and the lanes the case is meaningful on.
EDGE_CASES: list[dict] = [
    # ---- location: the BILL nationwide bug and its neighbours ----
    {
        "id": "us_nationwide_visible",
        "label": "US-nationwide 'United States' is reachable for a US city seeker",
        "row": {"job_title": "Staff Data Engineer", "company": "Arine",
                "location": "United States", "job_url": "u/nat"},
        "filters": _f(),
        "expected": {"outcome": "visible"},
        "lanes": ["work", "quests"],
    },
    {
        "id": "multi_location_trailing_us_visible",
        "label": "Multi-location list ending in '; United States' is nationwide",
        "row": {"job_title": "Staff Data Engineer", "company": "Teamworks",
                "location": "Draper, Utah, United States; San Jose, California, "
                            "United States; United States", "job_url": "u/multi"},
        "filters": _f(),
        "expected": {"outcome": "visible"},
        "lanes": ["work", "quests"],
    },
    {
        "id": "new_york_hidden_for_la",
        "label": "'New York, United States' is a specific NY role, hidden for an LA seeker",
        "row": {"job_title": "Staff Data Engineer", "company": "NYCo",
                "location": "New York, United States", "job_url": "u/ny"},
        "filters": _f(),
        "expected": {"outcome": "hidden", "stage": "location"},
        "lanes": ["work", "quests"],
    },
    {
        "id": "foreign_remote_intl_hidden",
        "label": "'Remote, India' remote_scope=intl is not reachable from the US",
        "row": {"job_title": "Staff Data Engineer", "company": "RemoteCo",
                "location": "Remote, India", "remote_scope": "intl",
                "is_remote": True, "job_url": "u/india"},
        "filters": _f(),
        "expected": {"outcome": "hidden", "stage": "location"},
        "lanes": ["work", "quests"],
    },
    {
        "id": "placeless_visible",
        "label": "A placeless row (unknown is not elsewhere) stays reachable",
        "row": {"job_title": "Data Engineer", "company": "NoPlace",
                "location": "", "job_url": "u/placeless"},
        "filters": _f(),
        "expected": {"outcome": "visible"},
        "lanes": ["work", "quests"],
    },
    # ---- salary: hourly annualization and per-gig session pay ----
    {
        "id": "hourly_50_clears_60k_floor_visible",
        "label": "Hourly $50 annualizes to $104k, clears a $60k floor (kept)",
        "row": {"job_title": "Data Engineer", "company": "HourCo",
                "location": "United States", "salary_min": 50.0, "salary_max": 50.0,
                "salary_period": "hourly", "job_url": "u/hourly60"},
        "filters": _f(salary_min=60000),
        "expected": {"outcome": "visible"},
        "lanes": ["work"],
    },
    {
        "id": "hourly_50_below_150k_floor_hidden",
        "label": "Hourly $50 ($104k annualized) is below a $150k floor (dropped)",
        "row": {"job_title": "Data Engineer", "company": "HourCo2",
                "location": "United States", "salary_min": 50.0, "salary_max": 50.0,
                "salary_period": "hourly", "job_url": "u/hourly150"},
        "filters": _f(salary_min=150000),
        "expected": {"outcome": "hidden", "stage": "salary"},
        "lanes": ["work"],
    },
    {
        "id": "session_pay_kept_visible",
        "label": "Per-gig 'session' pay is not a rate: kept like no-stated-pay",
        "row": {"job_title": "Data Engineer", "company": "GigCo",
                "location": "United States", "salary_min": 200.0,
                "salary_period": "session", "job_url": "u/session"},
        "filters": _f(salary_min=150000),
        "expected": {"outcome": "visible"},
        "lanes": ["work"],
    },
    # ---- anchored freshness: prose, epoch, RFC-2822 ----
    {
        "id": "reposted_3_days_hidden_by_3",
        "label": "'Reposted 3 Days Ago' + old date_found reads ~9d, dropped by a 3-day window",
        "row": {"job_title": "Data Engineer", "company": "RelCo",
                "location": "United States", "date_posted": "Reposted 3 Days Ago",
                "date_found_days_ago": 6, "job_url": "u/rel3"},
        "filters": _f(posted_within_days=3, freshness_explicit=False),
        "expected": {"outcome": "hidden", "stage": "anchored_freshness"},
        "lanes": ["work"],
    },
    {
        "id": "reposted_3_days_visible_by_30",
        "label": "The same '~9d old' row is fresh under a 30-day window",
        "row": {"job_title": "Data Engineer", "company": "RelCo",
                "location": "United States", "date_posted": "Reposted 3 Days Ago",
                "date_found_days_ago": 6, "job_url": "u/rel30"},
        "filters": _f(posted_within_days=30, freshness_explicit=False),
        "expected": {"outcome": "visible"},
        "lanes": ["work"],
    },
    {
        "id": "bare_epoch_recent_visible",
        "label": "A bare epoch timestamp is parsed to a real age; a recent one is fresh",
        "row": {"job_title": "Data Engineer", "company": "EpochCo",
                "location": "United States", "date_posted_epoch_days_ago": 2,
                "job_url": "u/epoch"},
        "filters": _f(posted_within_days=30, freshness_explicit=False),
        "expected": {"outcome": "visible"},
        "lanes": ["work"],
    },
    {
        "id": "rfc2822_unknown_kept_saved_default",
        "label": "An RFC-2822 date is unreadable by the age parser; kept under a saved window",
        "row": {"job_title": "Data Engineer", "company": "RfcCo",
                "location": "United States", "date_posted": "Mon, 21 Jul 2025 00:00:00 GMT",
                "date_found_days_ago": 2, "job_url": "u/rfc"},
        "filters": _f(posted_within_days=30, freshness_explicit=False),
        "expected": {"outcome": "visible"},
        "lanes": ["work"],
    },
    {
        "id": "rfc2822_unknown_dropped_explicit",
        "label": "The same unreadable date drops under an EXPLICIT freshness request",
        "row": {"job_title": "Data Engineer", "company": "RfcCo",
                "location": "United States", "date_posted": "Mon, 21 Jul 2025 00:00:00 GMT",
                "date_found_days_ago": 2, "job_url": "u/rfc2"},
        "filters": _f(posted_within_days=30, freshness_explicit=True),
        "expected": {"outcome": "hidden", "stage": "anchored_freshness"},
        "lanes": ["work"],
    },
    # ---- dead link ----
    {
        "id": "dead_url_status_hidden",
        "label": "A dead url_status is dropped by the dead-link stage",
        "row": {"job_title": "Data Engineer", "company": "DeadCo",
                "location": "United States", "url_status": "dead", "job_url": "u/dead"},
        "filters": _f(),
        "expected": {"outcome": "hidden", "stage": "dead_link"},
        "lanes": ["work", "quests"],
    },
]


# The cross-source duplicate pair is a two-row case: both share a dedup key, one
# is kept. Seeded together; the tracer must keep the richer/direct copy and drop
# the other. Career/work lane only (side quests do not cross-source dedup).
DEDUP_PAIR = {
    "id": "cross_source_duplicate_pair",
    "label": "Two sources, one opening: the direct+dated copy is kept, the other dropped",
    "keeper": {
        "job_title": "Data Engineer", "company": "DupCo", "source": "greenhouse",
        "location": "United States",
        "job_url": "https://boards.greenhouse.io/dupco/jobs/9001",
        "description": "x" * 240, "date_posted_iso_days_ago": 1,
        "date_found_days_ago": 1,
    },
    "loser": {
        "job_title": "Data Engineer", "company": "DupCo", "source": "linkedin",
        "location": "United States",
        "job_url": "https://www.linkedin.com/jobs/view/9002",
        "description": "", "date_found_days_ago": 1,
    },
    "filters": _f(),
    "lane": "work",
    "keeper_expected": {"outcome": "visible"},
    "loser_expected": {"outcome": "hidden", "stage": "dedup"},
}
