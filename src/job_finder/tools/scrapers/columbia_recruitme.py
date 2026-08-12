"""Columbia RecruitMe (body kind): CUIMC clinical and behavioral studies in NYC.

RecruitMe is Columbia University Irving Medical Center's volunteer portal,
a server-rendered Drupal site (live-verified 2026-07-14, "223 Studies Now
Enrolling"). The search index lists every study, 200 per page::

    GET https://recruit.cumc.columbia.edu/search?page=N   (page=0..)

Each ``div.search-item`` carries the lay title linking to the study's
detail page (``/studyinfopage/{id}``), the condition ("Healthy
Volunteers", "Neurological Disorders"), the investigator, a status chip,
and a truncated lay summary. "Currently Recruiting" items sort before
"Closed" ones (page 0 was all recruiting, page 1 was 23 recruiting then
177 closed), so paging stops at the first page with no recruiting items.

Compensation lives ONLY in the detail page's "Additional Study
Information" prose, and only some studies state it. Pay honesty rules:

- "up to $X" maps to salary_max ONLY: a ceiling is never a promised floor.
- A single stated hourly rate ("$25 per hour") maps to min=max with
  salary_period "hourly"; it is never annualized.
- A lone flat amount right after a compensation verb ("compensated $100")
  maps to min=max unless a per-unit word follows it.
- Everything else emits no salary keys: per-visit schedules ("$150 for
  infusion visits; $50 or $75 for blood draws"), half-ranges ("between
  $15/hour" with no upper bound), and silence. The verbatim pay sentence
  always rides in quest.pay_note, so the poster can still quote the
  source.

The detail page also states sponsor, study length, clinic visits, IRB
number, an NCT id when registered, and who is enrolling ("Female Patients
Only" restricts; "Male and Female Patients" means everyone, say nothing).
A ``closed_to_enrollment`` marker there overrides a stale listing status.
Neither the index nor detail pages state posted or end dates, so rows
never emit date_posted and are always rolling; the "Added On" table on
the homepage covers only the latest 10 studies.

robots.txt is the stock Drupal file: it disallows ``/search/`` (the core
search module, trailing slash) but not the Views page at ``/search``, and
leaves ``/studyinfopage/`` unrestricted. The full index is returned, while a
bounded newest subset is enriched from detail pages with a 1s gap. This keeps
the source inside Questboard's 60-second boundary without dropping studies.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _HEADERS, _TIMEOUT

logger = logging.getLogger(__name__)

_BASE = "https://recruit.cumc.columbia.edu"
_SEARCH_URL = _BASE + "/search?page={page}"
_MAX_PAGES = 12  # 1751 studies / 200 per page live; a runaway pager stops here
_DELAY_S = 1.0
_DETAIL_ENRICH_CAP = 20
_RECRUITING = "currently recruiting"

_MONEY = r"\$\s*(\d[\d,]*(?:\.\d+)?)"
_MONEY_RE = re.compile(_MONEY)
_UP_TO_RE = re.compile(r"up\s+to\s+" + _MONEY, re.IGNORECASE)
_HOURLY_RE = re.compile(_MONEY + r"\s*(?:/\s*(?:hr|hour)\b|\s(?:per|an)\s+hour\b)", re.IGNORECASE)
_FLAT_RE = re.compile(r"(?:compensated?|compensation\s+of|earn|receive|paid|pays?)\s+" + _MONEY, re.IGNORECASE)
_PER_UNIT_RE = re.compile(r"\s*(?:/|per\b|each\b|an?\s+(?:hour|visit|session|night)\b)", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
# ages only with an explicit age marker; bare "2 to 3 years" is a duration
_AGES_RE = re.compile(
    r"\bages?d?\s+(\d{1,2})\s*(?:to|through|and|[-\u2013])\s*(\d{1,2})\b"
    r"|(?<![\w$])(\d{1,2})\s*(?:to|through|[-\u2013])\s*(\d{1,2})\s+years\s+(?:old|of\s+age)\b",
    re.IGNORECASE,
)

# detail-table labels (colon stripped) -> quest keys, verbatim values
_DETAIL_FIELDS = {
    "Sponsor": "sponsor",
    "Study Length": "study_length",
    "Clinic Visits": "clinic_visits",
    "IRB Number": "irb_number",
    "U.S. Govt. ID": "nct_id",
}


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _fetch_search_page(page: int) -> str | None:
    """GET one search index page; None on any failure."""
    url = _SEARCH_URL.format(page=page)
    try:
        # the shared headers advertise JSON; this site is plain HTML
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("RecruitMe search page %d fetch failed: %s", page, exc)
        return None


def _fetch_detail(url: str) -> str | None:
    """GET one studyinfopage; None on any failure."""
    try:
        resp = requests.get(
            url, headers={**_HEADERS, "Accept": "text/html"}, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        logger.warning("RecruitMe detail %s fetch failed: %s", url, exc)
        return None


def _text(node, selector: str) -> str:
    found = node.select_one(selector)
    return _clean(found.get_text(" ", strip=True)) if found else ""


def _parse_search_items(html: str) -> list[dict]:
    """One index page to raw item dicts (title/url/status/condition/...)."""
    items: list[dict] = []
    for div in BeautifulSoup(html, "html.parser").select("div.search-item"):
        link = div.select_one(".views-field-field-lay-title a")
        title = _clean(link.get_text(" ", strip=True)) if link else ""
        if not link or not link.get("href") or not title:
            continue
        items.append({
            "title": title,
            "url": urljoin(_BASE, link["href"]),
            "status": _text(div, "span.recruitme-status"),
            "condition": _text(div, ".views-field-field-parent-category span.field-content"),
            "investigator": _text(div, ".views-field-recruitme-investigator-name span.field-content"),
            "teaser": _text(div, ".views-field-field-lay-summary span.field-content"),
        })
    return items


def _parse_detail(html: str) -> dict:
    """One studyinfopage to labeled fields + full summary; closed flag wins."""
    soup = BeautifulSoup(html, "html.parser")
    info: dict = {"closed": soup.select_one(".closed_to_enrollment") is not None}
    for tr in soup.select("table.ct_details_table tr"):
        label = _text(tr, "td.ct_details_label").rstrip(":")
        value = _text(tr, "td.ct_details_text")
        if not value:
            continue
        if label in _DETAIL_FIELDS:
            info[_DETAIL_FIELDS[label]] = value
        elif label == "Enrolling":
            info["enrolling"] = value
    summary = soup.select_one("div.ct_details_summary")
    if summary is not None:
        header = summary.select_one(".ct_details_summary_header")
        if header is not None:
            header.extract()
        info["summary"] = _clean(summary.get_text(" ", strip=True))
    return info


def _stated_comp(text: str) -> dict:
    """Salary keys only for unambiguous stated pay; {} for everything else."""
    ceilings = [float(m.replace(",", "")) for m in _UP_TO_RE.findall(text)]
    if ceilings:
        return {"salary_max": max(ceilings), "salary_source": "reported"}
    if len(_MONEY_RE.findall(text)) != 1:
        return {}  # per-visit schedules; a total here would be invented
    if re.search(r"between\s+\$", text, re.IGNORECASE):
        return {}  # "between $15/hour" states no upper bound
    m = _HOURLY_RE.search(text)
    if m:
        rate = float(m.group(1).replace(",", ""))
        return {
            "salary_min": rate,
            "salary_max": rate,
            "salary_period": "hourly",
            "salary_source": "reported",
        }
    m = _FLAT_RE.search(text)
    if m and not _PER_UNIT_RE.match(text[m.end():]):
        amount = float(m.group(1).replace(",", ""))
        return {"salary_min": amount, "salary_max": amount, "salary_source": "reported"}
    return {}


def _pay_sentence(text: str) -> str:
    """The source's own pay sentence, verbatim; "" when none states a figure."""
    for sentence in _SENTENCE_RE.split(text):
        if _MONEY_RE.search(sentence):
            return sentence.strip()
    return ""


def _ages(text: str) -> tuple[int, int] | None:
    m = _AGES_RE.search(text)
    if not m:
        return None
    low, high = (int(g) for g in m.groups() if g)
    if not 0 < low <= high <= 110:
        return None
    return low, high


def _sex(enrolling: str) -> str:
    male = re.search(r"\bmale\b", enrolling, re.IGNORECASE) is not None
    female = re.search(r"\bfemale\b", enrolling, re.IGNORECASE) is not None
    if male == female:
        return ""  # "Male and Female Patients" means everyone; say nothing
    return "Female" if female else "Male"


def _truncate(text: str) -> str:
    if len(text) <= 400:
        return text
    return text[:400].rsplit(" ", 1)[0] + "..."


def _row_from_item(item: dict) -> dict:
    """One recruiting search item to a body-kind quest row."""
    condition = item["condition"]
    healthy = "healthy" in condition.casefold()
    quest: dict = {}
    if condition:
        quest["condition"] = condition
    if healthy:
        quest["healthy_volunteers"] = True
    if item["investigator"]:
        quest["investigator"] = item["investigator"]
    row: dict = {
        "title": item["title"],
        "company": "Columbia University Irving Medical Center",
        "location": "New York, NY",
        "url": item["url"],
        "source": "columbia_recruitme",
        "vertical": "body",
        "description": item["teaser"],
        # recruiting studies fill on a rolling basis; no page states an end date
        "is_rolling": True,
        # healthy-volunteer studies need no prior condition
        "first_quest_ok": healthy,
    }
    if quest:
        row["quest"] = quest
    return row


def _enrich_from_detail(row: dict, detail: dict) -> None:
    if not detail:
        return
    quest = row.setdefault("quest", {})
    for key in _DETAIL_FIELDS.values():
        if detail.get(key):
            quest[key] = detail[key]
    sex = _sex(detail.get("enrolling", ""))
    if sex:
        quest["sex"] = sex
    summary = detail.get("summary", "")
    if not summary:
        return
    row["description"] = _truncate(summary)
    row.update(_stated_comp(summary))
    pay = _pay_sentence(summary)
    if pay:
        quest["pay_note"] = pay
    ages = _ages(summary)
    if ages:
        quest["age_min"], quest["age_max"] = ages


@register_scraper(
    name="columbia_recruitme",
    display_name="Columbia RecruitMe",
    url="https://recruit.cumc.columbia.edu",
    description="Columbia University clinical and behavioral studies enrolling in NYC, with stated compensation only",
    category="body",
    kind="body",
    # the crawl covers the recruiting set, which sorts first; sweeps should
    # pass max_results at or above the site's enrolling count (223 live)
    # so absence keeps meaning removal
    full_snapshot=True,
    # studies open and close over days, one polite crawl a day
    refresh_hours=24,
    allowed_url_hosts=("recruit.cumc.columbia.edu",),
    enabled_by_default=False,
)
def search_columbia_recruitme(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch recruiting studies from Columbia RecruitMe.

    ``roles`` is ignored on purpose: studies are not career titles. The full
    index set is kept; up to 20 newest rows receive detail-page enrichment.
    """
    logger.info("Fetching recruiting studies from Columbia RecruitMe...")

    rows: list[dict] = []
    seen_urls: set[str] = set()
    for page in range(_MAX_PAGES):
        if len(rows) >= max_results:
            break
        if page:
            time.sleep(_DELAY_S)
        html = _fetch_search_page(page)
        if not html:
            break
        items = _parse_search_items(html)
        if not items:
            break
        recruiting = 0
        for item in items:
            if item["status"].casefold() != _RECRUITING:
                continue
            recruiting += 1
            if item["url"] in seen_urls or len(rows) >= max_results:
                continue
            seen_urls.add(item["url"])
            rows.append(_row_from_item(item))
        if not recruiting:
            break  # recruiting sorts first; the rest of the index is closed

    results: list[dict] = []
    enriched = 0
    for row in rows:
        if enriched >= _DETAIL_ENRICH_CAP:
            results.append(row)
            continue
        if enriched:
            time.sleep(_DELAY_S)
        enriched += 1
        html = _fetch_detail(row["url"])
        detail = _parse_detail(html) if html else {}
        if detail.get("closed"):
            continue  # the detail page outranks a stale listing status
        _enrich_from_detail(row, detail)
        results.append(row)

    logger.info("Columbia RecruitMe: %d recruiting studies", len(results))
    return results
