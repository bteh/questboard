"""Profile + archetype helpers for Launchboard.

This module is intentionally separate from `src/job_finder/config/` (which
holds raw YAML data + the existing `profile_schema.py`) so the higher-level
helper code lives next to the application code that consumes it.
"""

from __future__ import annotations

from .archetypes import (
    Archetype,
    list_archetypes,
    load_archetype,
    apply_archetype,
)

__all__ = [
    "Archetype",
    "list_archetypes",
    "load_archetype",
    "apply_archetype",
]
