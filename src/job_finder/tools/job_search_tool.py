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

_DEFAULT_BOARDS = ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]


def search_jobs(
    search_term: str,
    location: str = "Los Angeles, CA",
    results_wanted: int = 25,
    hours_old: int = 336,
    is_remote: bool | None = None,
    country: str = "USA",
    linkedin_fetch_description: bool = True,
    boards: list[str] | None = None,
    distance: int | None = None,
) -> list[dict]:
    """Search multiple job boards via JobSpy and return normalised dicts.

    Returns a *list of dicts* (not JSON string) for direct Python consumption.
    Each dict has keys: title, company, location, url, source, description,
    salary_min, salary_max, date_posted, is_remote, company_size.

    Parameters
    ----------
    linkedin_fetch_description : bool
        Fetch full job page per LinkedIn result (~2-3s each).  The pipeline
        passes ``False`` during fast search and relies on descriptions from
        other boards.  CLI callers default to ``True`` for richer data.
    boards : list[str] or None
        JobSpy site names to scrape.  Defaults to Indeed, LinkedIn, Glassdoor,
        ZipRecruiter, and Google.  Configurable via ``job_boards`` in YAML.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []

    site_names = boards or _DEFAULT_BOARDS

    try:
        scrape_kwargs = dict(
            site_name=site_names,
            search_term=search_term,
            google_search_term=f"{search_term} jobs near {location}",
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=country,
            linkedin_fetch_description=linkedin_fetch_description,
        )
        # Only pass is_remote when explicitly True/False (not None)
        # JobSpy Pydantic model rejects None
        if is_remote is not None:
            scrape_kwargs["is_remote"] = bool(is_remote)
        if distance is not None:
            scrape_kwargs["distance"] = distance

        jobs_df: pd.DataFrame = scrape_jobs(**scrape_kwargs)

        if jobs_df.empty:
            return []

        jobs_list: list[dict] = []
        for _, row in jobs_df.iterrows():
            # Handle URL fallback properly (pandas NaN)
            url = row.get("job_url")
            if pd.isna(url) or not url:
                url = row.get("job_url_direct", "")

            loc_str = _safe_str(row.get("location", ""))
            loc_lower = loc_str.lower()
            raw_remote = _safe_bool(row.get("is_remote"))

            # Fix is_remote: hybrid jobs are NOT remote
            if any(kw in loc_lower for kw in ("hybrid", "in-office", "on-site")):
                is_remote_val = False
            elif raw_remote or "remote" in loc_lower:
                is_remote_val = True
            else:
                is_remote_val = False

            job = {
                "title": _safe_str(row.get("title", "")),
                "company": _safe_str(
                    row.get("company_name", row.get("company", ""))
                ),
                "location": loc_str,
                "url": _safe_str(url),
                "source": _safe_str(row.get("site", "")),
                "description": _safe_str(row.get("description", ""))[:3000],
                "salary_min": _safe_float(row.get("min_amount")),
                "salary_max": _safe_float(row.get("max_amount")),
                "date_posted": _safe_str(row.get("date_posted", "")),
                "is_remote": is_remote_val,
                "company_size": _safe_str(
                    row.get("company_num_employees", "")
                ),
            }
            jobs_list.append(job)

        return jobs_list

    except Exception as e:
        logger.error("Job search failed for '%s' in %s: %s", search_term, location, e)
        return []
