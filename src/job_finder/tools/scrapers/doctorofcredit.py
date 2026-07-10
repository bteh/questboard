"""Doctor of Credit (house kind): live bank and brokerage bonuses via WP REST.

DoC is the churning community's canonical list (r/churning treats it as the
source of record). The WordPress REST API is open::

    GET https://www.doctorofcredit.com/wp-json/wp/v2/posts
        ?categories=142,215&per_page=..&orderby=modified&order=desc

Category 142 is the maintained "current bank account bonuses" set and 215 is
brokerage bonuses. Live-verified quirks (2026-07-09):

- Posts that die are usually retitled "[Expired] ..." before they leave the
  category, so the TITLE is the liveness gate, not category membership.
- Roundup posts ("A List Of Churnable Bank Account Bonuses") carry no "$"
  in the title; requiring a stated amount filters them naturally.
- A leading bracket names availability ("[NV only] ...", "[Targeted, NJ &
  PA only] ..."); it becomes the row's location verbatim.
- Post bodies open with an "Offer at a glance" block (Maximum bonus amount,
  Availability, Direct deposit required, Hard/soft pull, ChexSystems, ...).
  That block is the source's own honesty data; a subset becomes the
  description and the quest fields.

Pay renders only as titled: "$250" maps to an exact figure, tiered titles
("$100/$150/$350") map to the stated min and max, and "Up To $2,000" maps
to a maximum only, never a promised floor.

Absence semantics for the trust layer: an offer leaving category 142 (or
gaining the [Expired] title) is this source's expiry signal.
"""

from __future__ import annotations

import html
import logging
import re

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json

logger = logging.getLogger(__name__)

_API_URL = "https://www.doctorofcredit.com/wp-json/wp/v2/posts"
# current bank bonuses (142) + brokerage bonuses (215), both DoC-maintained
_CATEGORIES = "142,215"
_FIELDS = "id,date,title,link,content"

_AMOUNT_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)")
_BRACKET_PREFIX_RE = re.compile(r"^\[([^\]]+)\]\s*")
_TAG_RE = re.compile(r"<[^>]+>")

# The glance block's own labels, in the source's wording. Parsed as
# label-to-next-label spans over tag-stripped text.
_GLANCE_LABELS = (
    "Maximum bonus amount",
    "Availability",
    "Direct deposit required",
    "Additional requirements",
    "Hard/soft pull",
    "ChexSystems",
    "Credit card funding",
    "Monthly fees",
    "Early account termination fee",
    "Expiration date",
)
_GLANCE_SPLIT_RE = re.compile(
    "(" + "|".join(re.escape(label) for label in _GLANCE_LABELS) + r")\s*:?\s*"
)

# glance fields that make the scannable description, in reading order
_DESC_FIELDS = (
    "Availability",
    "Direct deposit required",
    "Hard/soft pull",
    "ChexSystems",
    "Monthly fees",
    "Expiration date",
)


def _glance(content_html: str) -> dict[str, str]:
    """The "Offer at a glance" block as {label: value}, empty when absent."""
    text = html.unescape(_TAG_RE.sub(" ", content_html or ""))
    idx = text.lower().find("offer at a glance")
    if idx < 0:
        return {}
    window = text[idx : idx + 1400]
    parts = _GLANCE_SPLIT_RE.split(window)
    out: dict[str, str] = {}
    for label, value in zip(parts[1::2], parts[2::2]):
        cleaned = re.sub(r"\s+", " ", value).strip(" .;,")
        if cleaned:
            out[label] = cleaned[:140]
    return out


def _title_pay(title: str) -> dict:
    """Salary fields from the stated title amounts; empty dict when none."""
    amounts = [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(title)]
    if not amounts:
        return {}
    if "up to" in title.lower():
        return {"salary_max": max(amounts), "salary_source": "reported"}
    return {
        "salary_min": min(amounts),
        "salary_max": max(amounts),
        "salary_source": "reported",
    }


def _normalize_post(post: dict) -> dict | None:
    """One WP post object to a house-kind quest row, or None to skip."""
    raw_title = (post.get("title") or {}).get("rendered") or ""
    title = re.sub(r"\s+", " ", html.unescape(raw_title)).strip()
    link = post.get("link") or ""
    if not title or not link:
        return None
    if "[expired" in title.lower():
        return None

    pay = _title_pay(title)
    if not pay:
        return None  # roundup or news post, not a single stated bonus

    location = ""
    m = _BRACKET_PREFIX_RE.match(title)
    if m:
        location = m.group(1).strip()
        title = title[m.end():].strip()

    glance = _glance((post.get("content") or {}).get("rendered") or "")
    if not location and glance.get("Availability"):
        location = glance["Availability"]

    description = " ".join(
        f"{label}: {glance[label]}." for label in _DESC_FIELDS if label in glance
    )
    quest = {
        key: glance[label]
        for label, key in (
            ("Hard/soft pull", "pull"),
            ("ChexSystems", "chexsystems"),
            ("Direct deposit required", "direct_deposit"),
            ("Early account termination fee", "termination_fee"),
        )
        if label in glance
    }

    row: dict = {
        "title": title,
        "company": "Doctor of Credit",
        "location": location,
        "url": link,
        "source": "doctorofcredit",
        "vertical": "house",
        "description": description,
        # No date_posted on purpose: DoC re-runs years-old posts for live
        # offers, so the publish date reads "posted 30 months ago" on a
        # bonus that is current TODAY. Saying nothing beats misleading;
        # liveness is category membership, not the byline.
        **pay,
    }
    if quest:
        row["quest"] = quest
    return row


@register_scraper(
    name="doctorofcredit",
    display_name="Doctor of Credit",
    url="https://www.doctorofcredit.com",
    description="Live bank and brokerage bonuses with the source's own hard-pull and ChexSystems facts",
    category="house",
    kind="house",
    enabled_by_default=False,
)
def search_doctorofcredit(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch current bank and brokerage bonuses from Doctor of Credit.

    ``roles`` is ignored on purpose: bonuses are not career titles. Ordered
    by modified so refreshed offers (DoC bumps posts when terms change)
    surface first.
    """
    logger.info("Fetching current bonuses from Doctor of Credit...")
    data = _get_json(
        _API_URL,
        params={
            "categories": _CATEGORIES,
            "per_page": str(min(max(max_results, 1), 100)),
            "orderby": "modified",
            "order": "desc",
            "_fields": _FIELDS,
        },
    )
    if not isinstance(data, list):
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()
    for post in data:
        if len(results) >= max_results:
            break
        if not isinstance(post, dict):
            continue
        row = _normalize_post(post)
        if row is None or row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        results.append(row)

    logger.info("Doctor of Credit: %d live bonuses", len(results))
    return results
