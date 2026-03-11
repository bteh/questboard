"""Backward-compat shim — all scoring logic lives in ``job_finder.scoring``."""

from job_finder.scoring.core import score_job_basic
from job_finder.scoring.signals import (
    CULTURE_ENTERPRISE_SIGNALS,
    CULTURE_STARTUP_SIGNALS,
    HIGH_COMP_SIGNALS,
    LEADERSHIP_KEYWORDS,
    PLATFORM_BUILDING_KEYWORDS,
    TECHNICAL_KEYWORDS,
    TIER_BASELINES,
    TRAJECTORY_ENTERPRISE_SIGNALS,
    TRAJECTORY_STARTUP_SIGNALS,
)

__all__ = [
    "score_job_basic",
    "TECHNICAL_KEYWORDS",
    "LEADERSHIP_KEYWORDS",
    "PLATFORM_BUILDING_KEYWORDS",
    "HIGH_COMP_SIGNALS",
    "TRAJECTORY_STARTUP_SIGNALS",
    "TRAJECTORY_ENTERPRISE_SIGNALS",
    "CULTURE_STARTUP_SIGNALS",
    "CULTURE_ENTERPRISE_SIGNALS",
    "TIER_BASELINES",
]
