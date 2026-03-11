"""Hacker News "Who is Hiring?" — Algolia API scraper."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _strip_html

logger = logging.getLogger(__name__)


@register_scraper(
    name="hackernews",
    display_name="Hacker News",
    url="https://news.ycombinator.com",
    description="Jobs from monthly Who is Hiring? threads",
    category="community",
)
def search_hn_hiring(
    roles: list[str] | None = None,
    max_results: int = 50,
    **kwargs,
) -> list[dict]:
    """Fetch jobs from the latest HN 'Who is hiring?' thread."""
    logger.info("Fetching HN 'Who is Hiring?' thread...")

    now = datetime.now(timezone.utc)
    current_month = now.strftime("%B %Y")
    prev_month = (now.replace(day=1) - __import__("datetime").timedelta(days=1)).strftime("%B %Y")

    thread_id = None
    for query_month in [current_month, prev_month]:
        search_url = "https://hn.algolia.com/api/v1/search"
        params = {
            "query": f"Ask HN: Who is hiring? ({query_month})",
            "tags": "ask_hn",
            "hitsPerPage": 3,
        }
        data = _get_json(search_url, params=params)
        if data and data.get("hits"):
            for hit in data["hits"]:
                title = hit.get("title", "")
                if "who is hiring" in title.lower() and query_month.split()[0].lower() in title.lower():
                    thread_id = hit.get("objectID")
                    break
        if thread_id:
            break

    if not thread_id:
        data = _get_json(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={
                "query": "Who is hiring",
                "tags": "ask_hn",
                "hitsPerPage": 5,
            },
        )
        if data and data.get("hits"):
            for hit in data["hits"]:
                if "who is hiring" in hit.get("title", "").lower():
                    thread_id = hit["objectID"]
                    break

    if not thread_id:
        logger.warning("Could not find HN 'Who is Hiring?' thread")
        return []

    logger.info("Found HN thread ID: %s", thread_id)

    thread_data = _get_json(f"https://hn.algolia.com/api/v1/items/{thread_id}")
    if not thread_data or "children" not in thread_data:
        logger.warning("Could not fetch HN thread comments")
        return []

    results: list[dict] = []
    for comment in thread_data["children"]:
        text = comment.get("text", "")
        if not text:
            continue

        plain = _strip_html(text)
        first_line = plain.split("\n")[0] if "\n" in plain else plain[:200]

        pipe_parts = [p.strip() for p in first_line.split("|")]
        if len(pipe_parts) >= 2:
            company = pipe_parts[0]
            title = ""
            location = ""
            is_remote = False
            for part in pipe_parts[1:]:
                pl = part.lower()
                if any(kw in pl for kw in ["remote", "onsite", "hybrid"]):
                    is_remote = "remote" in pl
                    if not location:
                        location = part
                elif any(kw in pl for kw in [
                    "engineer", "developer", "data", "manager", "director",
                    "designer", "lead", "head", "vp", "cto", "founding",
                    "hiring", "multiple", "senior", "staff", "principal",
                ]):
                    if not title:
                        title = part
                elif re.match(r"^[A-Z][a-z]", part) and len(part) < 50:
                    if not location:
                        location = part

            if not title:
                title = pipe_parts[1] if len(pipe_parts) > 1 else company

            if not _match_roles(title, roles):
                continue

            url_match = re.search(r'https?://[^\s<"]+', text)
            job_url = url_match.group(0) if url_match else ""

            results.append({
                "title": title[:200],
                "company": company[:100],
                "location": location or "Not specified",
                "url": job_url,
                "source": "hackernews",
                "description": plain[:3000],
                "salary_min": None,
                "salary_max": None,
                "date_posted": comment.get("created_at", ""),
                "is_remote": is_remote,
                "company_size": "",
            })

            if len(results) >= max_results:
                break

    logger.info("HN Who is Hiring: found %d matching jobs", len(results))
    return results
