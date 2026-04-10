"""Profession archetype loader.

Each archetype is a YAML file in src/job_finder/config/archetypes/<slug>.yaml
that contains a small delta on top of the default profile (scoring weights,
keywords, scraper allowlist, target roles, comp targets) tailored to one
career family — healthcare, education, government, trades, nonprofit, etc.

The motivation is the user-friendliness ask: a non-technical user opening
Launchboard for the first time shouldn't have to fight tech-coded defaults
to find a nursing job. The archetype picker on the first-run wizard maps
their profession to one of these presets, which swaps the defaults so the
search and scoring feel native to their field.

This module is the data-layer side of that work. The wizard wiring (so the
user actually picks an archetype on first run) is a separate piece of work
that consumes `list_archetypes()` and `load_archetype(slug)`.

Public API
----------

list_archetypes() -> list[Archetype]
    Discover every archetype YAML in the directory and return its metadata
    (slug, name, description, emoji) without parsing the full body. Use
    this to populate a picker UI.

load_archetype(slug) -> dict
    Read a specific archetype YAML and return the full parsed config.

apply_archetype(base_profile, slug) -> dict
    Merge an archetype's overrides into a base profile dict (typically the
    contents of `default.yaml`). Returns a new dict — does not mutate the
    input. Lists are replaced wholesale; nested dicts are merged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Resolve the archetypes dir relative to this file rather than CWD so the
# loader works regardless of where the process was launched from (CLI,
# pytest, FastAPI worker, etc).
_ARCHETYPES_DIR = Path(__file__).resolve().parent.parent / "config" / "archetypes"


@dataclass(frozen=True)
class Archetype:
    """Lightweight metadata for a single archetype.

    Used to populate a picker UI without parsing the full YAML body. Slug
    is the file stem (e.g. ``"healthcare"``), name + description + emoji
    come from the ``archetype:`` block at the top of the file.
    """

    slug: str
    name: str
    description: str
    emoji: str = ""

    @property
    def display(self) -> str:
        if self.emoji:
            return f"{self.emoji}  {self.name}"
        return self.name


def list_archetypes() -> list[Archetype]:
    """Return metadata for every archetype YAML in the directory.

    Parses only the ``archetype:`` header block, not the full body, so this
    is fast enough to call on every onboarding render. Returns an empty
    list if the directory is missing (e.g. fresh checkout that hasn't been
    seeded yet) so callers can degrade gracefully.
    """
    if not _ARCHETYPES_DIR.is_dir():
        return []

    out: list[Archetype] = []
    for path in sorted(_ARCHETYPES_DIR.glob("*.yaml")):
        slug = path.stem
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Skipping malformed archetype %s: %s", slug, exc)
            continue
        meta = data.get("archetype") or {}
        out.append(
            Archetype(
                slug=slug,
                name=str(meta.get("name") or slug.title()),
                description=str(meta.get("description") or ""),
                emoji=str(meta.get("emoji") or ""),
            )
        )
    return out


def load_archetype(slug: str) -> dict[str, Any]:
    """Load a single archetype YAML by slug.

    Raises FileNotFoundError if the slug doesn't exist. Raises
    yaml.YAMLError if the file is malformed.
    """
    path = _ARCHETYPES_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Unknown archetype: {slug!r} (looked in {_ARCHETYPES_DIR})")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Archetype {slug} did not parse to a dict")
    return data


def apply_archetype(base_profile: dict[str, Any], slug: str) -> dict[str, Any]:
    """Merge an archetype's overrides on top of a base profile.

    Returns a new dict — does not mutate the input. Merge rules:

    - Top-level keys present in the archetype replace the base.
    - Nested dicts (``scoring``, ``keywords``, ``compensation``) are
      merged key-by-key, so the archetype only has to override what
      it cares about.
    - Lists are replaced wholesale (no concat) — this matches user
      intent: when an archetype says ``enabled_scrapers: [...]`` it
      means "these and only these", not "these in addition to base".

    The archetype's ``archetype:`` metadata block is preserved at the
    top level so downstream consumers can introspect which preset is
    active.
    """
    arch = load_archetype(slug)
    merged: dict[str, Any] = dict(base_profile)

    for key, value in arch.items():
        if key == "archetype":
            # Stash metadata so the UI can show "Currently using:
            # Healthcare 🏥" without having to re-load.
            merged["archetype"] = value
            continue
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = {**existing, **value}
        else:
            merged[key] = value

    return merged
