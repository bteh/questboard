"""ClinicalTrials.gov -- healthy-volunteer research studies via the public v2 API.

The registry API at ``https://clinicaltrials.gov/api/v2/studies`` is free and
unauthenticated. We ask for RECRUITING studies that accept healthy volunteers
(``filter.advanced=AREA[HealthyVolunteers]true``), optionally near a point
(``filter.geo=distance(lat,lon,50mi)``), and page via ``nextPageToken``. Each
study nests everything under ``protocolSection``: identification (nctId,
briefTitle), status (studyFirstPostDateStruct), sponsor, brief summary,
design (studyType, phases, enrollment) and eligibility (healthyVolunteers,
minimumAge/maximumAge), plus per-site locations with geoPoints.

The API carries NO compensation field, so rows never emit salary keys and the
stored description is the protocol's own briefSummary verbatim. This is a
quest scraper (vertical "study"): explicitly invoked only, never swept into
the career pipeline.
"""

from __future__ import annotations

import logging
import math
import re

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _strip_html

logger = logging.getLogger(__name__)

_API_URL = "https://clinicaltrials.gov/api/v2/studies"
_PAGE_SIZE = 50
_MAX_PAGES = 5  # 5 pages x 50 = 250 studies ceiling per call

# Only the modules we read -- trims each page to a fraction of the full payload.
_FIELDS = ",".join((
    "protocolSection.identificationModule",
    "protocolSection.statusModule",
    "protocolSection.sponsorCollaboratorsModule",
    "protocolSection.descriptionModule.briefSummary",
    "protocolSection.designModule",
    "protocolSection.eligibilityModule",
    "protocolSection.contactsLocationsModule.locations",
))

_AGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(year|month|week|day)", re.IGNORECASE)
_AGE_UNIT_YEARS = {"year": 1.0, "month": 1 / 12, "week": 1 / 52, "day": 1 / 365}


def _age_years(raw: object) -> int | None:
    """Parse an eligibility age like '18 Years' or '6 Months' into whole years."""
    if not isinstance(raw, str):
        return None
    m = _AGE_RE.search(raw)
    if not m:
        return None
    return int(float(m[1]) * _AGE_UNIT_YEARS[m[2].lower()])


def _phase_label(phases: object) -> str | None:
    """Human phase label: ['PHASE2'] -> 'Phase 2', ['PHASE1','PHASE2'] joined.

    'NA' (behavioral/observational designs) carries no phase information and
    is dropped rather than surfaced as a fake phase.
    """
    if not isinstance(phases, list):
        return None
    labels: list[str] = []
    for p in phases:
        if not isinstance(p, str) or p == "NA":
            continue
        m = re.fullmatch(r"(EARLY_)?PHASE(\d)", p)
        if m:
            labels.append(f"{'Early ' if m[1] else ''}Phase {m[2]}")
    return "/".join(labels) or None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two lat/lon points."""
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (
        math.sin((rlat2 - rlat1) / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin((rlon2 - rlon1) / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def _nearest_site(
    locations: object, lat: float | None, lon: float | None,
) -> dict | None:
    """Pick the study site to display: nearest to (lat, lon) when given.

    Sites actively RECRUITING are preferred over not-yet/completed sites.
    Without a reference point the first preferred site wins (the API lists
    sites in protocol order). Sites lacking a geoPoint sort last.
    """
    if not isinstance(locations, list):
        return None
    sites = [loc for loc in locations if isinstance(loc, dict)]
    if not sites:
        return None
    recruiting = [s for s in sites if s.get("status") == "RECRUITING"]
    candidates = recruiting or sites
    if lat is None or lon is None:
        return candidates[0]

    def distance(site: dict) -> float:
        geo = site.get("geoPoint") or {}
        try:
            return _haversine_miles(lat, lon, float(geo["lat"]), float(geo["lon"]))
        except (KeyError, TypeError, ValueError):
            return float("inf")

    return min(candidates, key=distance)


def _format_location(site: dict | None) -> str:
    """'City, State' for US sites, 'City, Country' elsewhere."""
    if not site:
        return ""
    city = (site.get("city") or "").strip()
    country = (site.get("country") or "").strip()
    region = (site.get("state") or "").strip() if country == "United States" else country
    return ", ".join(p for p in (city, region) if p)


def _normalize_study(
    study: dict, lat: float | None = None, lon: float | None = None,
) -> dict | None:
    """Map one API v2 study object to a quest row, or None when unusable."""
    ps = study.get("protocolSection") if isinstance(study, dict) else None
    if not isinstance(ps, dict):
        return None
    ident = ps.get("identificationModule") or {}
    nct_id = ident.get("nctId")
    title = ident.get("briefTitle") or ""
    if not nct_id or not title:
        return None

    sponsor = (ps.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
    org = ident.get("organization") or {}
    company = sponsor.get("name") or org.get("fullName") or ""

    site = _nearest_site(
        (ps.get("contactsLocationsModule") or {}).get("locations"), lat, lon,
    )

    elig = ps.get("eligibilityModule") or {}
    design = ps.get("designModule") or {}
    healthy = bool(elig.get("healthyVolunteers"))

    # Only values the protocol actually states land in the quest dict.
    quest: dict = {"healthy_volunteers": healthy}
    age_min = _age_years(elig.get("minimumAge"))
    if age_min is not None:
        quest["age_min"] = age_min
    age_max = _age_years(elig.get("maximumAge"))
    if age_max is not None:
        quest["age_max"] = age_max
    phase = _phase_label(design.get("phases"))
    if phase:
        quest["phase"] = phase
    study_type = design.get("studyType")
    if study_type:
        quest["study_type"] = study_type
    headcount = (design.get("enrollmentInfo") or {}).get("count")
    if isinstance(headcount, int):
        quest["headcount"] = headcount
    sex = elig.get("sex")
    if isinstance(sex, str) and sex and sex != "ALL":
        quest["sex"] = sex

    row = {
        "title": title,
        "company": company,
        "location": _format_location(site),
        "url": f"https://clinicaltrials.gov/study/{nct_id}",
        "source": "clinicaltrials",
        "vertical": "body",
        # The protocol's own summary, whitespace-collapsed. No pay language is
        # added: the API has no compensation field.
        "description": _strip_html(ps.get("descriptionModule", {}).get("briefSummary") or ""),
        # Recruiting studies enroll on a rolling basis; there is no event date.
        "is_rolling": True,
        # Healthy-volunteer studies need no prior condition or experience.
        "first_quest_ok": healthy,
        "quest": quest,
    }
    # studyFirstPostDateStruct is the registry's stated first-post date. When
    # it is absent we omit date_posted; downstream stamps date_confidence.
    post_date = (ps.get("statusModule") or {}).get("studyFirstPostDateStruct") or {}
    if post_date.get("date"):
        row["date_posted"] = post_date["date"]
    return row


@register_scraper(
    name="clinicaltrials",
    display_name="ClinicalTrials.gov",
    url="https://clinicaltrials.gov",
    description="Research studies recruiting healthy volunteers via the ClinicalTrials.gov v2 API",
    category="body",
    # recruiting statuses move slowly
    refresh_hours=24,
    allowed_url_hosts=("clinicaltrials.gov",),
    allowed_url_paths=("/study/",),
    enabled_by_default=False,
    # A clinical trial rents your BODY (screenings, confinement, doses);
    # focus groups and interviews sell your opinion. The communities have
    # self-sorted the same way (r/plassing vs r/focusgroups), so this
    # source moved from the think lane to body (2026-07-09). New rows
    # store vertical="body"; the alembic data revision refiles old rows.
    kind="body",
    # recruiting studies churn slowly; the fetch is windowed, so use age
    stale_after_days=45,
)
def search_clinicaltrials(
    roles: list[str] | None = None,
    max_results: int = 50,
    query: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_miles: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch recruiting healthy-volunteer studies from ClinicalTrials.gov.

    ``roles`` is accepted for the shared scraper calling convention but unused:
    studies are not role-titled, and quest scrapers only run when a caller
    names them. ``query`` maps to the API's ``query.term`` for topic searches
    ("sleep", "nutrition"). ``lat``/``lon`` (with ``radius_miles``) scope
    results to sites near a point and pick the nearest site for the location.
    """
    params: dict[str, str] = {
        "filter.advanced": "AREA[HealthyVolunteers]true",
        "filter.overallStatus": "RECRUITING",
        "pageSize": str(min(max_results, _PAGE_SIZE)),
        "fields": _FIELDS,
    }
    if query:
        params["query.term"] = query
    if lat is not None and lon is not None:
        params["filter.geo"] = f"distance({lat},{lon},{radius_miles}mi)"
    else:
        # the registry is global (a Guangzhou trial reached the live board);
        # without a geo hint, keep the board's default audience reachable
        params["query.locn"] = "United States"

    logger.info("Fetching healthy-volunteer studies from ClinicalTrials.gov...")
    results: list[dict] = []
    page_token: str | None = None
    for _ in range(_MAX_PAGES):
        if len(results) >= max_results:
            break
        page_params = dict(params)
        if page_token:
            page_params["pageToken"] = page_token
        data = _get_json(_API_URL, params=page_params)
        if not isinstance(data, dict):
            break
        studies = data.get("studies")
        if not isinstance(studies, list) or not studies:
            break
        for raw in studies:
            if len(results) >= max_results:
                break
            row = _normalize_study(raw, lat, lon)
            if row:
                results.append(row)
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    logger.info("ClinicalTrials.gov: found %d recruiting studies", len(results))
    return results
