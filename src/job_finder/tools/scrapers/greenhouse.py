"""Greenhouse — Bulk company board scraper via JSON API."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles, _strip_html

logger = logging.getLogger(__name__)

_GREENHOUSE_COMPANIES = [
    # AI / ML
    "anthropic", "openai", "cohere", "mistral", "huggingface",
    "scaleai", "deepmind", "inflection", "adept", "character",
    "wandb", "runwayml", "stabilityai", "perplexityai", "anyscale",
    "modal", "together", "replicatehq", "midjourney",
    # Data infrastructure
    "databricks", "dbt-labs", "fivetran", "confluent", "starburst",
    "snowflake", "clickhouse", "motherduck", "tabular", "preset",
    "astronomer", "airbyte", "meltano", "census", "hightouch",
    "montecarlodata", "atlan", "greatexpectations",
    "tecaborhq",  # Tecton — slug needs verification
    "dbtlabsinc",  # dbt Labs alternate slug
    # Fintech
    "stripe", "plaid", "ramp", "brex", "affirm", "coinbase",
    "mercury", "rippling", "carta", "nerdwallet", "chime",
    "sardine",
    # Developer tools / Cloud
    "figma", "notion", "airtable", "vercel", "netlify",
    "gitlab", "hashicorp", "snyk", "datadog", "pagerduty",
    "cloudflare", "postman", "linear", "retool", "supabase",
    "planetscale", "neondatabase", "railway", "render", "temporal",
    "webflow",
    # Security
    "wiz", "lacework", "orcasecurity",
    # Consumer / Marketplace
    "airbnb", "instacart", "duolingo", "pinterest", "discord",
    "reddit", "spotify", "lyft", "doordash", "faire",
    # Enterprise / SaaS
    "hubspot", "sqsp", "gusto", "docusign", "grammarly",
    "canva", "miro", "loom", "calendly", "lattice",
    "amplitude", "segment", "mixpanel", "launchdarkly", "contentful",
    # Deep tech / Hardware
    "anduril", "palantir", "rivian", "relativity", "astranis",
    "samsara", "verkada", "zipline", "crusoe", "gecko-robotics",
]


def _fetch_company_jobs(slug: str, roles: list[str] | None) -> list[dict]:
    """Fetch matching jobs for a single Greenhouse company board."""
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if not data or "jobs" not in data:
        return []

    jobs: list[dict] = []
    for job in data["jobs"]:
        title = job.get("title", "")
        if not _match_roles(title, roles):
            continue

        loc = job.get("location", {})
        location = loc.get("name", "") if isinstance(loc, dict) else str(loc)

        # Extract description from HTML content
        content = job.get("content", "")
        description = _strip_html(content) if content else ""

        jobs.append({
            "title": title,
            "company": slug.replace("-", " ").title(),
            "location": location,
            "url": job.get("absolute_url", ""),
            "source": "greenhouse",
            "description": description,
            "salary_min": None,
            "salary_max": None,
            "date_posted": job.get("updated_at", ""),
            "is_remote": "remote" in location.lower(),
            "company_size": "",
        })

    return jobs


@register_scraper(
    name="greenhouse",
    display_name="Greenhouse",
    url="https://greenhouse.io",
    description="Direct job listings from top company boards",
    category="ats",
)
def search_greenhouse(
    roles: list[str] | None = None,
    max_results: int = 50,
    companies: list[str] | None = None,
    watchlist_companies: list[str] | None = None,
    **kwargs,
) -> list[dict]:
    """Fetch jobs directly from Greenhouse boards API for known companies."""
    company_list = list(companies or _GREENHOUSE_COMPANIES)
    if watchlist_companies:
        company_list.extend(s for s in watchlist_companies if s not in company_list)
    logger.info("Fetching from Greenhouse API for %d companies...", len(company_list))

    results: list[dict] = []
    workers = min(len(company_list), 10)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_company_jobs, slug, roles): slug
            for slug in company_list
        }
        for future in as_completed(futures):
            try:
                jobs = future.result()
                results.extend(jobs)
            except Exception as e:
                slug = futures[future]
                logger.warning("Greenhouse/%s failed: %s", slug, e)

    results = results[:max_results]
    logger.info("Greenhouse: found %d matching jobs across %d companies",
                len(results), len(company_list))
    return results
