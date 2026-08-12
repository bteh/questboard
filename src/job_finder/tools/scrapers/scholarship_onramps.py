"""Curated official scholarship and education-benefit on-ramps.

Directories are useful for breadth, but the safest high-value opportunities
deserve a direct card to the sponsor or government page.  Every claim below
was checked on the linked official page on 2026-08-05.  Dated programs are
returned only inside their verified application window, and carry event_end
so they disappear from the board after the deadline even before the next
source-expiry sweep.

CareerOneStop is the U.S. Department of Labor's free finder rather than an
individual award.  Its data is licensed from Gale/Cengage, so this source does
not copy the directory; it provides one on-ramp to the official search tool
and tells the user to confirm each result with its sponsor.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from job_finder.tools.scrapers._registry import register_scraper

logger = logging.getLogger(__name__)

_CHECKED = "2026-08-05"

_ONRAMPS: list[dict] = [
    {
        "title": "Search the Department of Labor scholarship finder",
        "company": "CareerOneStop",
        "location": "United States",
        "url": "https://www.careeronestop.org/Toolkit/Training/find-scholarships.aspx",
        "description": (
            "Use CareerOneStop's free Scholarship Finder from the U.S. Department of Labor. "
            "It lists more than 9,500 scholarships, fellowships, grants, and other financial "
            "aid and can narrow by education level, location, award type, and affiliations "
            f"including military or veteran status (checked {_CHECKED})."
        ),
        "bring": "your education level, location, field, and affiliations",
        "application_effort": "quick",
        "application_effort_note": (
            "Set a few search filters; each scholarship result has its own separate application."
        ),
        "criteria": [
            "Anyone can use the free finder; each listed scholarship sets its own eligibility rules."
        ],
        "catch": (
            "the directory says sponsor deadlines and eligibility can change; verify every "
            "result on the sponsor's page, read its privacy terms, and never pay for access"
        ),
        "first_quest_ok": True,
        "rolling": True,
    },
    {
        "title": "Apply for the $20,000 Coca-Cola Scholars scholarship",
        "company": "Coca-Cola Scholars Foundation",
        "location": "United States",
        "url": "https://www.coca-colascholarsfoundation.org/apply/",
        "description": (
            "The 2027 Coca-Cola Scholars Program awards 150 achievement-based $20,000 "
            "scholarships to current high school students graduating in the 2026-2027 "
            "school year who plan to attend an accredited U.S. post-secondary institution. "
            f"The official first-round application is open through September 30, 2026 (checked {_CHECKED})."
        ),
        "bring": (
            "a B/3.0 GPA and your school, activities, service, and employment details; "
            "phase 1 needs no essay, transcript, or recommendation"
        ),
        "application_effort": "quick",
        "application_effort_note": (
            "The first round asks for school, activity, service, and work details but no essay, "
            "transcript, or recommendation."
        ),
        "criteria": [
            "Be a current high-school student graduating in the 2026-2027 school year.",
            "Plan to attend an accredited U.S. post-secondary institution.",
            "Have at least a B/3.0 GPA and meet the foundation's stated residency rules.",
        ],
        "catch": (
            "only eligible 2026-2027 high-school graduates in the stated U.S. areas may "
            "apply, and selection emphasizes leadership and service"
        ),
        "opened": "2026-08-03",
        "deadline": "2026-09-30",
        "salary_min": 20000.0,
        "salary_max": 20000.0,
        "first_quest_ok": True,
    },
    {
        "title": "Apply for the VFW Help A Hero Scholarship",
        "company": "VFW and Student Veterans of America",
        "location": "United States",
        "url": "https://www.vfw.org/Scholarship/",
        "description": (
            "The VFW's Sport Clips Help A Hero Scholarship awards up to $5,000 for tuition "
            "and fees to qualifying service members and veterans in an accredited, VA-approved "
            f"post-secondary program. Spring-semester applications run August 1-November 15 (checked {_CHECKED})."
        ),
        "bring": "proof of service, school or program enrollment, and financial need",
        "application_effort": "some_prep",
        "application_effort_note": (
            "Gather service, enrollment, and financial-need information for the online application."
        ),
        "criteria": [
            "Be a U.S. citizen and a qualifying service member or veteran.",
            "Have completed basic and advanced training and currently hold, or have separated at, E-5 or below.",
            "Attend an accredited, VA-approved post-secondary program.",
        ],
        "catch": (
            "applicants must be U.S. citizens who completed training and currently hold or "
            "separated at E-5 or below; funds go directly to the school"
        ),
        "opened": "2026-08-01",
        "deadline": "2026-11-15",
        "salary_max": 5000.0,
        "first_quest_ok": False,
    },
    {
        "title": "Apply for the fully funded Schwarzman Scholars master's",
        "company": "Schwarzman Scholars",
        "location": "Anywhere; study in Beijing, China",
        "url": "https://www.schwarzmanscholars.org/admissions/application-instructions/",
        "description": (
            "Schwarzman Scholars is a fully funded one-year master's in global affairs at "
            "Tsinghua University in Beijing. The program covers tuition, fees, room and board, "
            "travel, course supplies, health insurance, and a personal stipend. The U.S./Global "
            f"application closes September 9, 2026 at 3 p.m. EDT (checked {_CHECKED})."
        ),
        "bring": "an undergraduate degree, resume, transcripts, essays, and recommendation letters",
        "application_effort": "involved",
        "application_effort_note": (
            "Prepare transcripts, a resume, essays, recommendation letters, and the full degree application."
        ),
        "criteria": [
            "Hold an undergraduate degree before enrollment.",
            "Be age 18-28 on August 1, 2027.",
            "Demonstrate English proficiency and be available for the residential year in Beijing.",
        ],
        "catch": (
            "applicants must be 18-28 by August 1, 2027, proficient in English, and ready for "
            "a highly selective residential degree in Beijing"
        ),
        "opened": "2026-04-08",
        "deadline": "2026-09-09",
        "pay_note": "Fully funded master's, including a personal stipend",
        "first_quest_ok": False,
    },
    {
        "title": "Claim education benefits through the Fry Scholarship",
        "company": "U.S. Department of Veterans Affairs",
        "location": "United States",
        "url": "https://www.va.gov/family-and-caregiver-benefits/education-and-careers/fry-scholarship/",
        "description": (
            "The VA's Fry Scholarship can provide eligible children or surviving spouses of "
            "qualifying service members up to 36 months of benefits for tuition and fees, "
            "housing, books, supplies, exams, licensing or certification, work study, and some "
            f"rural moves. Applications are accepted online or by mail (checked {_CHECKED})."
        ),
        "bring": "your qualifying family and service information plus your school or training plan",
        "application_effort": "some_prep",
        "application_effort_note": (
            "Gather the qualifying family and service history, then complete the VA education-benefit form."
        ),
        "criteria": [
            "Be a child or surviving spouse covered by the VA's qualifying line-of-duty or service-connected-death rules."
        ],
        "catch": (
            "eligibility is limited to children or surviving spouses under the VA's specific "
            "line-of-duty and service-connected-death rules"
        ),
        "pay_note": "Up to 36 months of eligible education benefits",
        "first_quest_ok": False,
        "rolling": True,
    },
    {
        "title": "Add up to $30,000 with the Rogers STEM Scholarship",
        "company": "U.S. Department of Veterans Affairs",
        "location": "United States",
        "url": "https://www.va.gov/education/other-va-education-benefits/stem-scholarship/",
        "description": (
            "The VA's Edith Nourse Rogers STEM Scholarship adds up to nine months of benefits "
            "or $30,000, whichever comes first, for eligible veterans and Fry Scholars in "
            "qualifying undergraduate STEM, health clinical-training, or teaching-certification "
            f"paths. The VA accepts applications online and awards monthly (checked {_CHECKED})."
        ),
        "bring": "your degree or training details and a statement of remaining GI Bill or Fry benefits",
        "application_effort": "some_prep",
        "application_effort_note": (
            "Provide degree or training details and your remaining GI Bill or Fry benefit information."
        ),
        "criteria": [
            "Be an eligible veteran or Fry Scholar in a qualifying STEM, clinical-training, or teaching-certification path.",
            "Most applicants must have six months or less of Post-9/11 GI Bill or Fry benefits remaining.",
        ],
        "catch": (
            "most applicants need six months or less of Post-9/11 GI Bill or Fry benefits left; "
            "the VA prioritizes eligible applicants and does not guarantee an award"
        ),
        "salary_max": 30000.0,
        "first_quest_ok": False,
        "rolling": True,
    },
]


def _today() -> date:
    """Wrapped so tests can freeze the clock."""
    return datetime.now(timezone.utc).date()


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _row(entry: dict) -> dict | None:
    today = _today()
    opened = _as_date(entry.get("opened"))
    deadline = _as_date(entry.get("deadline"))
    if opened is not None and today < opened:
        return None
    if deadline is not None and today > deadline:
        return None

    quest: dict[str, object] = {
        "bring": entry["bring"],
        "catch": entry["catch"],
        "application_effort": entry["application_effort"],
        "application_effort_note": entry["application_effort_note"],
        "criteria": entry["criteria"],
    }
    if deadline is not None:
        quest["apply_by"] = deadline.isoformat()
    if entry.get("pay_note"):
        quest["pay_note"] = entry["pay_note"]

    row: dict = {
        "title": entry["title"],
        "company": entry["company"],
        "location": entry["location"],
        "url": entry["url"],
        "source": "scholarship_onramps",
        "vertical": "scholarship",
        "description": entry["description"],
        "date_posted": opened.isoformat() if opened is not None else "",
        "is_rolling": bool(entry.get("rolling", deadline is None)),
        "first_quest_ok": bool(entry.get("first_quest_ok", False)),
        "quest": quest,
    }
    if opened is not None:
        row["date_confidence"] = "exact"
    if deadline is not None:
        row["event_end"] = deadline.isoformat()
    for key in ("salary_min", "salary_max"):
        if entry.get(key) is not None:
            row[key] = entry[key]
    if row.get("salary_min") is not None or row.get("salary_max") is not None:
        row["salary_source"] = "reported"
    return row


@register_scraper(
    name="scholarship_onramps",
    display_name="Official scholarship programs",
    url="https://www.careeronestop.org/Toolkit/Training/find-scholarships.aspx",
    description="Curated sponsor and government scholarship pages with independently enforced application windows",
    category="scholarship",
    kind="scholarship",
    full_snapshot=True,
    refresh_hours=168,
    enabled_by_default=False,
    allowed_url_hosts=(
        "careeronestop.org",
        "coca-colascholarsfoundation.org",
        "vfw.org",
        "schwarzmanscholars.org",
        "va.gov",
    ),
)
def search_scholarship_onramps(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Return currently actionable, official scholarship on-ramps."""
    results: list[dict] = []
    for entry in _ONRAMPS:
        if len(results) >= max(0, max_results):
            break
        row = _row(entry)
        if row is not None:
            results.append(row)
    logger.info("scholarship_onramps: %d currently actionable rows", len(results))
    return results
