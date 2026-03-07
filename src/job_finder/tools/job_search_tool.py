"""JobSpy-powered job search — plain function, no framework dependency."""

from __future__ import annotations

import json
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# -- Safe type helpers (pandas NaN handling) --------------------------------

def _safe_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string, handling NaN and None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    return str(value)


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_bool(value: Any) -> bool:
    """Safely convert to bool, treating NaN as False."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return bool(value)


# -- Main search function --------------------------------------------------

def search_jobs(
    search_term: str,
    location: str = "Los Angeles, CA",
    results_wanted: int = 25,
    hours_old: int = 336,
    is_remote: bool | None = None,
    country: str = "USA",
) -> list[dict]:
    """Search multiple job boards via JobSpy and return normalised dicts.

    Returns a *list of dicts* (not JSON string) for direct Python consumption.
    Each dict has keys: title, company, location, url, source, description,
    salary_min, salary_max, date_posted, is_remote, company_size.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []

    site_names = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]

    try:
        jobs_df: pd.DataFrame = scrape_jobs(
            site_name=site_names,
            search_term=search_term,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            is_remote=is_remote,
            country_indeed=country,
        )

        if jobs_df.empty:
            return []

        jobs_list: list[dict] = []
        for _, row in jobs_df.iterrows():
            # Handle URL fallback properly (pandas NaN)
            url = row.get("job_url")
            if pd.isna(url) or not url:
                url = row.get("job_url_direct", "")

            job = {
                "title": _safe_str(row.get("title", "")),
                "company": _safe_str(
                    row.get("company_name", row.get("company", ""))
                ),
                "location": _safe_str(row.get("location", "")),
                "url": _safe_str(url),
                "source": _safe_str(row.get("site", "")),
                "description": _safe_str(row.get("description", ""))[:3000],
                "salary_min": _safe_float(row.get("min_amount")),
                "salary_max": _safe_float(row.get("max_amount")),
                "date_posted": _safe_str(row.get("date_posted", "")),
                "is_remote": _safe_bool(row.get("is_remote")),
                "company_size": _safe_str(
                    row.get("company_num_employees", "")
                ),
            }
            jobs_list.append(job)

        return jobs_list

    except Exception as e:
        logger.error("Job search failed for '%s' in %s: %s", search_term, location, e)
        return []
