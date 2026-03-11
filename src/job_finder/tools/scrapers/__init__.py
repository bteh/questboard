"""Scraper plugin package — auto-discovers all scraper modules on import.

Public API:
    register_scraper  — decorator for new scrapers
    get_registry      — full registry dict
    get_all_metadata  — list of ScraperMeta for all sources
    run_scrapers      — run selected scrapers and merge results
"""

from __future__ import annotations

import importlib
import pkgutil

from job_finder.tools.scrapers._registry import (
    ScraperMeta,
    get_all_metadata,
    get_registry,
    register_scraper,
    run_scrapers,
)

# Auto-import all sibling modules to trigger their @register_scraper decorators
for _finder, _name, _ispkg in pkgutil.iter_modules(__path__):
    if not _name.startswith("_"):
        importlib.import_module(f"{__name__}.{_name}")

# Register JobSpy boards as metadata-only (no search_fn — handled by job_search_tool)
_JOBSPY_BOARDS = [
    ("indeed",        "Indeed",        "https://indeed.com",        "Job listings via Indeed"),
    ("linkedin",      "LinkedIn",      "https://linkedin.com",      "Professional network job listings"),
    ("glassdoor",     "Glassdoor",     "https://glassdoor.com",     "Jobs with company reviews & salaries"),
    ("zip_recruiter", "ZipRecruiter",  "https://ziprecruiter.com",  "AI-powered job matching"),
    ("google",        "Google Jobs",   "https://google.com/jobs",   "Google job search aggregator"),
]

_registry = get_registry()
for _name, _display, _url, _desc in _JOBSPY_BOARDS:
    if _name not in _registry:
        _registry[_name] = ScraperMeta(
            name=_name,
            display_name=_display,
            url=_url,
            description=_desc,
            category="jobspy",
            enabled_by_default=True,
            search_fn=None,
        )

__all__ = [
    "register_scraper",
    "get_registry",
    "get_all_metadata",
    "run_scrapers",
    "ScraperMeta",
]
