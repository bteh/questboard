"""Shared rules for public-employer career sources (EdJoin, CSU Careers).

Government, school, and university postings share shapes the startup ATS
boards never see: pay stated as a monthly or hourly range in prose, postings
open only to current employees, and student-only jobs. Every special case
for that family lives here, and each rule is pinned in
tests/test_public_sector_rules.py by the real posting that motivated it.
"""

from __future__ import annotations

import re

from job_finder.us_states import extract_state_codes

_REMOTE_WORDS = {"remote", "anywhere", "worldwide"}


def wants_california(locations: list[str] | None) -> bool:
    """Whether a California-only source is worth fetching for these places.

    No saved places means no place filter. A place naming another state, or
    remote alone, means a California-only board has nothing for this user.
    A bare city with no state could be anywhere, so it gets the fetch and the
    pipeline's place filter decides.
    """
    if not locations:
        return True
    for raw in locations:
        loc = (raw or "").strip()
        if not loc or loc.lower() in _REMOTE_WORDS:
            continue
        codes = extract_state_codes(loc)
        if not codes or "CA" in codes:
            return True
    return False


_PERIOD_RE = re.compile(
    r"\b(hourly|hours?|hr|daily|days?|weekly|weeks?|monthly|months?|mo|annually|annual|yearly|years?)\b",
    re.IGNORECASE,
)
_PERIOD_BY_STEM = {"h": "hourly", "d": "daily", "w": "weekly", "m": "monthly", "a": "annual", "y": "annual"}


def period_from_words(text: str | None) -> str | None:
    """Map the first stated pay period ("Per Hour", "monthly", "Annually") to
    the shared salary_period vocabulary, or None when nothing is stated.

    Whole words only: "$5,274-5,597 monthly Work Schedule: Monday" is monthly
    (Cal Poly Pomona, 2026-10-08), never daily.
    """
    m = _PERIOD_RE.search(text or "")
    return _PERIOD_BY_STEM[m.group(1)[0].lower()] if m else None


def job_type_from(text: str | None) -> str:
    """'Full Time' / 'Part Time' to the JobSpy job_type spelling, else ''."""
    lowered = (text or "").lower().replace("-", " ")
    if "full time" in lowered:
        return "fulltime"
    if "part time" in lowered:
        return "parttime"
    return ""


_MONEY_RE =re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_BARE_NUMBER_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def _to_float(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def money_amounts(text: str | None) -> list[float]:
    """Dollar amounts in a stated pay field, in order.

    EdJoin's structured pay boxes carry step and range labels beside the
    money ("Step 1: $6,586", "(Range 38) $4,544.00"), so dollar-signed
    amounts win. A box with no dollar sign ("39.41") is a bare amount; its
    last number is the money, never the step label before it.
    """
    if not text:
        return []
    signed = [v for v in (_to_float(m) for m in _MONEY_RE.findall(text)) if v]
    if signed:
        return signed
    bare = [v for v in (_to_float(m) for m in _BARE_NUMBER_RE.findall(text)) if v]
    return bare[-1:]


# CSU postings state pay up to three ways. The hiring range is what an
# offer will actually be, so it wins over a ceiling, which wins over the
# full classification band; a bare "Salary Range"/"Salary:" is last.
# Phrasings are copied from the live feed (2026-10-08).
_HIRING = (
    r"(?:anticipated|expected) (?:salary )?hiring (?:salary )?range"
    r"|hiring (?:salary )?range|hiring rate|in the range of"
)
_CEILING = r"not (?:anticipated )?to exceed|will not exceed"
_BAND = r"classification (?:salary )?range"
_PLAIN = r"salary range|salary\s*:"
_PAY_LABEL_RE = re.compile(
    rf"(?P<hiring>{_HIRING})|(?P<ceiling>{_CEILING})|(?P<band>{_BAND})|(?P<plain>{_PLAIN})",
    re.IGNORECASE,
)
_LABEL_PRIORITY = ("hiring", "ceiling", "band", "plain")
_WINDOW_CHARS = 160
_PAREN_RE = re.compile(r"\([^)]*\)")
_PERIOD_PHRASE_RE = re.compile(
    r"\b(?:per|a|an)\s+(?:hour|day|week|month|year)\b|\b(?:hourly|monthly|annually|yearly|mo)\b\.?",
    re.IGNORECASE,
)
_BARE_HIGH_RE = re.compile(r"\s*(?:-|–|—|to)\s*(\d[\d,]*(?:\.\d+)?)")
_CONNECTORS = {"-", "–", "—", "to", "and"}
_ANNUAL_FLOOR = 20_000.0
# The period must sit right after the figure: "$5,507 - $6,677 per course for
# the ... Academic Year" (Cal State San Marcos lecturer) is per course, and
# "$104-$1,406 per session rate. The hourly..." is per session.
_PERIOD_REACH = 30
_SENTENCE_END_RE = re.compile(r"\.\s")


def _is_range_connector(between: str) -> bool:
    cleaned = _PERIOD_PHRASE_RE.sub(" ", _PAREN_RE.sub(" ", between))
    return cleaned.replace("*", " ").strip().lower() in _CONNECTORS


def _pay_in_window(window: str, kind: str) -> tuple[float | None, float, str] | None:
    amounts = list(_MONEY_RE.finditer(window))
    if not amounts:
        return None
    first = _to_float(amounts[0].group(1))
    if first is None:
        return None
    low: float | None = first
    high = first
    period_from = amounts[0].end()
    bare_high = _BARE_HIGH_RE.match(window, amounts[0].end())
    if bare_high:
        second = _to_float(bare_high.group(1))
        if second is None or second < first:
            return None
        high = second
        period_from = bare_high.end()
    elif len(amounts) > 1 and _is_range_connector(window[amounts[0].end():amounts[1].start()]):
        second = _to_float(amounts[1].group(1))
        if second is None or second < first:
            return None
        high = second
        period_from = amounts[1].end()
    elif kind == "ceiling":
        low = None
    tail = window[period_from:period_from + _PERIOD_REACH]
    tail = _SENTENCE_END_RE.split(tail, maxsplit=1)[0]
    period = period_from_words(tail)
    if period is None and high >= _ANNUAL_FLOOR:
        period = "annual"
    if period is None:
        return None
    return low, high, period


def stated_pay_range(text: str | None) -> tuple[float | None, float, str] | None:
    """(min, max, period) for labelled pay in posting prose.

    Only labelled pay counts; a dollar figure elsewhere (a signing bonus, an
    H-1B fee) is never pay. Each label reads up to the next label, so a
    hiring rate never borrows the classification band's numbers. A single
    stated figure is a point value, except after "not to exceed", where it
    is a ceiling (min None). An unstated period is accepted only for
    amounts that can only be annual.
    """
    if not text:
        return None
    hits = list(_PAY_LABEL_RE.finditer(text))
    for kind in _LABEL_PRIORITY:
        for i, hit in enumerate(hits):
            if hit.lastgroup != kind:
                continue
            stop = hits[i + 1].start() if i + 1 < len(hits) else len(text)
            window = text[hit.end():min(stop, hit.end() + _WINDOW_CHARS)]
            pay = _pay_in_window(window, kind)
            if pay:
                return pay
    return None


# Postings an outside applicant cannot apply to. Each pattern is pinned by
# the live title that motivated it (EdJoin, 2026-10-08).
_INTERNAL_ONLY_RES: tuple[re.Pattern[str], ...] = (
    # Irvine USD: "Specialist III: Tech Support - 11-Month (Current Employees)"
    re.compile(r"\bcurrent employees?\b", re.IGNORECASE),
    # Orange USD: "Accounting Technician I (OPEN TO OUSD EMPLOYEES ONLY)"
    re.compile(r"\bemployees only\b", re.IGNORECASE),
    # Pomona USD: "Research Technician - This position is limited to Classified Employees"
    re.compile(r"\blimited to [a-z ]{0,30}employees\b", re.IGNORECASE),
)


def is_internal_only(title: str | None) -> bool:
    """True when the title says only current employees may apply."""
    text = title or ""
    return any(rx.search(text) for rx in _INTERNAL_ONLY_RES)


# CSU work types that require being an enrolled student
# ("Waterfront Assistant- Solano Campus Student Assistant", 2026-10-08).
_STUDENT_ONLY_WORK_TYPES = (
    "student assistant",
    "graduate assistant",
    "teaching associate",
    "federal work study",
)


def is_student_only(work_type: str | None) -> bool:
    """True when every listed work type is a student or grad-student job."""
    parts = [p.strip().lower() for p in (work_type or "").split(",") if p.strip()]
    if not parts:
        return False
    return all(any(s in part for s in _STUDENT_ONLY_WORK_TYPES) for part in parts)
