"""Pydantic v2 models for YAML profile validation (Issue #5).

Provides ``validate_profile`` (raises on error) and ``validate_profile_safe``
(returns errors as strings) so config loading can degrade gracefully.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class KeywordsConfig(BaseModel):
    """Keyword lists used by the scorer to match against job descriptions."""

    technical: list[str] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    platform_building: list[str] = Field(default_factory=list)
    high_comp_signals: list[str] = Field(default_factory=list)


class CareerBaselineConfig(BaseModel):
    """Current position baseline for career-progression scoring."""

    current_title: str = ""
    current_level: str = "mid"
    current_tc: float = 0.0
    min_acceptable_tc: float = 0.0

    @field_validator("current_level", mode="before")
    @classmethod
    def _normalize_level(cls, v: Any) -> str:
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and item.strip():
                    return item.strip()
            return "mid"
        if isinstance(v, str) and v.strip():
            return v.strip()
        return "mid"


class CompensationConfig(BaseModel):
    """Compensation filters and expectations."""

    min_base: float = Field(default=0.0, ge=0)
    target_total_comp: float = Field(default=0.0, ge=0)
    include_equity: bool = False
    currency: str = "USD"
    pay_period: str = "annual"


class ScoringThresholdsConfig(BaseModel):
    """Score thresholds for recommendation buckets."""

    strong_apply: float = 70
    apply: float = 55
    maybe: float = 40


class ScoringConfig(BaseModel):
    """Scoring dimension weights and thresholds."""

    technical_skills: float = 0.25
    leadership_signal: float = 0.15
    comp_potential: float = 0.12
    platform_building: float = 0.13
    company_trajectory: float = 0.10
    culture_fit: float = 0.10
    career_progression: float = 0.15
    thresholds: ScoringThresholdsConfig | None = None


class WatchlistEntry(BaseModel):
    """A single watchlist company entry."""

    name: str
    slug: str = ""
    ats: str = "unknown"
    job_count: int = 0
    careers_url: str = ""

    model_config = {"extra": "allow"}


class ProfileInfo(BaseModel):
    """Optional top-level profile metadata."""

    name: str = ""
    description: str = ""
    resume_path: str = ""


class ResumeAnalysis(BaseModel):
    """Cached resume analysis metadata."""

    industry: str = ""
    seniority: str = ""
    years_experience: float = 0

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Top-level profile model
# ---------------------------------------------------------------------------

class ProfileConfig(BaseModel):
    """Full YAML profile schema.

    Starter profiles may begin blank and then be populated from resume analysis
    or manual UI edits. Everything else has sensible defaults.
    """

    target_roles: list[str] = Field(default_factory=list)
    keyword_searches: list[str] | None = None
    keywords: KeywordsConfig | None = None
    career_baseline: CareerBaselineConfig | None = None
    compensation: CompensationConfig | None = None
    scoring: ScoringConfig | None = None
    locations: list[str] | None = None
    watchlist: list[WatchlistEntry] | None = None
    profile: ProfileInfo | None = None
    resume_analysis: ResumeAnalysis | None = Field(
        default=None, alias="_resume_analysis"
    )

    model_config = {"extra": "allow", "populate_by_name": True}

    # -- validators --------------------------------------------------------

    @field_validator("target_roles", mode="before")
    @classmethod
    def _strip_empty_roles(cls, v: Any) -> list[str]:
        """Remove empty/blank strings from target_roles."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("target_roles must be a list of strings")
        cleaned = [s for s in v if isinstance(s, str) and s.strip()]
        return cleaned


# ---------------------------------------------------------------------------
# Weight-sum check (not a hard failure -- returns warnings)
# ---------------------------------------------------------------------------

_WEIGHT_TOLERANCE = 0.05


def _check_weight_sum(scoring: ScoringConfig | None) -> list[str]:
    """Return a list of warning strings if weights don't sum to ~1.0."""
    if scoring is None:
        return []
    total = (
        scoring.technical_skills
        + scoring.leadership_signal
        + scoring.comp_potential
        + scoring.platform_building
        + scoring.company_trajectory
        + scoring.culture_fit
        + scoring.career_progression
    )
    if abs(total - 1.0) > _WEIGHT_TOLERANCE:
        return [
            f"Scoring weights sum to {total:.4f}, expected ~1.0. "
            f"This may produce unexpected score distributions."
        ]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_profile(config: dict) -> ProfileConfig:
    """Parse and validate a profile dict.  Raises ``ValueError`` on failure."""
    return ProfileConfig.model_validate(config)


def validate_profile_safe(
    config: dict,
) -> tuple[ProfileConfig | None, list[str]]:
    """Parse and validate a profile dict without raising.

    Returns ``(profile, errors)`` where *errors* is a list of human-readable
    strings.  If the profile is structurally invalid, *profile* is ``None``
    and *errors* describes what went wrong.  If validation succeeds but
    weights don't sum to ~1.0, *profile* is returned along with a warning
    in *errors*.
    """
    errors: list[str] = []
    try:
        profile = ProfileConfig.model_validate(config)
    except Exception as exc:  # noqa: BLE001
        # Flatten Pydantic ValidationError into readable strings
        if hasattr(exc, "errors"):
            for err in exc.errors():  # type: ignore[union-attr]
                loc = " -> ".join(str(l) for l in err.get("loc", []))
                msg = err.get("msg", str(err))
                errors.append(f"{loc}: {msg}" if loc else msg)
        else:
            errors.append(str(exc))
        return None, errors

    # Non-fatal warnings
    warnings = _check_weight_sum(profile.scoring)
    return profile, warnings
