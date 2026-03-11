"""Centralized constants — single source of truth for statuses, recommendations, etc."""

from __future__ import annotations

# Application statuses (pipeline lifecycle)
STATUS_FOUND = "found"
STATUS_REVIEWED = "reviewed"
STATUS_APPLYING = "applying"
STATUS_APPLIED = "applied"
STATUS_INTERVIEWING = "interviewing"
STATUS_OFFER = "offer"
STATUS_REJECTED = "rejected"
STATUS_WITHDRAWN = "withdrawn"

ALL_STATUSES = (
    STATUS_FOUND,
    STATUS_REVIEWED,
    STATUS_APPLYING,
    STATUS_APPLIED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_WITHDRAWN,
)

# Scoring recommendations
REC_STRONG_APPLY = "STRONG_APPLY"
REC_APPLY = "APPLY"
REC_MAYBE = "MAYBE"
REC_SKIP = "SKIP"

ALL_RECOMMENDATIONS = (REC_STRONG_APPLY, REC_APPLY, REC_MAYBE, REC_SKIP)

# Company type tiers
COMPANY_FAANG_PLUS = "FAANG+"
COMPANY_BIG_TECH = "Big Tech"
COMPANY_ELITE_STARTUP = "Elite Startup"
COMPANY_GROWTH_STAGE = "Growth Stage"
COMPANY_EARLY_STARTUP = "Early Startup"
COMPANY_MIDSIZE = "Midsize"
COMPANY_ENTERPRISE = "Enterprise"
COMPANY_UNKNOWN = "Unknown"

ALL_COMPANY_TYPES = (
    COMPANY_FAANG_PLUS,
    COMPANY_BIG_TECH,
    COMPANY_ELITE_STARTUP,
    COMPANY_GROWTH_STAGE,
    COMPANY_EARLY_STARTUP,
    COMPANY_MIDSIZE,
    COMPANY_ENTERPRISE,
    COMPANY_UNKNOWN,
)

# Work types
WORK_REMOTE = "remote"
WORK_HYBRID = "hybrid"
WORK_ONSITE = "onsite"

# Scoring dimensions (key, label, default weight)
SCORE_DIMENSIONS = (
    ("technical_skills", "Technical Skills", 0.25),
    ("leadership_signal", "Leadership", 0.15),
    ("career_progression", "Career Progression", 0.15),
    ("platform_building", "Platform Building", 0.13),
    ("comp_potential", "Comp Potential", 0.12),
    ("company_trajectory", "Company Trajectory", 0.10),
    ("culture_fit", "Culture Fit", 0.10),
)

# Scoring thresholds (defaults — overridable per profile)
DEFAULT_STRONG_APPLY_THRESHOLD = 70
DEFAULT_APPLY_THRESHOLD = 55
DEFAULT_MAYBE_THRESHOLD = 40

# Application methods
METHOD_MANUAL = "manual"
METHOD_GREENHOUSE = "greenhouse"
METHOD_LEVER = "lever"
METHOD_LINKEDIN = "linkedin"

# Scraper categories
CATEGORY_JOBSPY = "jobspy"
CATEGORY_REMOTE = "remote"
CATEGORY_ATS = "ats"
CATEGORY_STARTUP = "startup"
CATEGORY_CRYPTO = "crypto"
CATEGORY_COMMUNITY = "community"
