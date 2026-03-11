"""Backward-compat shim — delegates to scraper registry.

Existing code that imports ``search_additional_sources`` from here
will continue to work unchanged.
"""

from __future__ import annotations

from typing import Any

from job_finder.tools.scrapers import run_scrapers


def search_additional_sources(
    roles: list[str] | None = None,
    max_results_per_source: int = 25,
    sources: list[str] | None = None,
    progress: Any = None,
) -> list[dict]:
    """Run all (or selected) additional scrapers and merge results."""
    return run_scrapers(
        names=sources,
        roles=roles,
        max_results=max_results_per_source,
        progress=progress,
    )
