"""Signal keyword lists and company tier baselines for job scoring.

All keyword/signal constants live here so dimension scorers and the
main ``score_job_basic`` function can import them without circular deps.
"""

from __future__ import annotations

# ── Technical skills ──────────────────────────────────────────────────────

TECHNICAL_KEYWORDS = [
    "dbt", "trino", "spark", "airflow", "python", "sql", "data modeling",
    "lakehouse", "iceberg", "snowflake", "databricks", "bigquery", "redshift",
    "kafka", "flink", "kubernetes", "docker", "terraform", "aws", "gcp",
    "azure", "postgresql", "etl", "elt", "data pipeline", "data warehouse",
    "data lake", "ci/cd", "git", "pandas", "pyspark",
]

# ── Leadership ────────────────────────────────────────────────────────────

LEADERSHIP_KEYWORDS = [
    # Universal leadership signals
    "manager", "head of", "director", "lead", "principal", "staff",
    "founding", "vp of", "build the team", "hire and mentor",
    "own the roadmap", "team lead", "people management",
    "supervise", "oversee", "manage a team", "direct reports",
    "cross-functional", "stakeholder management", "executive",
    "strategic planning", "budget", "p&l", "org design",
    # Domain-specific leadership (kept broad)
    "architect", "cto", "cmo", "cfo", "coo", "cro", "cpo", "cio",
    "vp engineering", "vp marketing", "vp sales", "vp operations",
    "director of engineering", "engineering manager",
    "creative director", "design director", "editorial director",
]

# ── Platform building (startup + enterprise growth) ───────────────────────

PLATFORM_BUILDING_KEYWORDS = [
    # Universal startup / new-build signals
    "greenfield", "from scratch", "v1", "0 to 1", "zero to one",
    "build the foundation", "establish best practices", "build out",
    "founding", "first hire", "first team member", "ground up",
    "launch", "stand up", "net-new", "ownership", "autonomy",
    # Enterprise growth signals
    "migration", "modernization", "re-architecture", "re-platform",
    "new initiative", "new team", "transformation",
    "build a new", "define the strategy", "vision",
    "new program", "new department", "new function", "new market",
    "go-to-market", "market entry", "expansion",
]

# ── High comp signals ─────────────────────────────────────────────────────

HIGH_COMP_SIGNALS = [
    "netflix", "nvidia", "airbnb", "stripe", "databricks", "snowflake",
    "confluent", "meta", "google", "apple", "amazon", "microsoft",
    "staff", "principal", "senior staff", "l6", "l7", "e6", "e7",
    "cto", "vp", "director",
    # Big-tech level ladders
    "l5", "l8", "e5", "e8", "ic5", "ic6", "ic7",
    # Equity / comp language
    "equity", "rsu", "stock options", "competitive compensation",
    "total compensation", "signing bonus",
]

# ── Company trajectory (startup + enterprise) ─────────────────────────────

TRAJECTORY_STARTUP_SIGNALS = [
    "series a", "series b", "series c", "series d", "series e",
    "raised", "funded", "growing", "scaling", "hiring", "expanding",
    "yc", "y combinator", "backed by", "venture",
]

TRAJECTORY_ENTERPRISE_SIGNALS = [
    "market leader", "fortune 500", "global", "worldwide",
    "industry leader", "established", "publicly traded",
    "revenue growth", "record revenue", "billion", "market cap",
    "expanding", "new office", "doubling", "growth trajectory",
]

# ── Culture fit (startup + enterprise) ────────────────────────────────────

CULTURE_STARTUP_SIGNALS = [
    "remote", "flexible", "async", "collaborative",
    "open source", "modern", "inclusive", "diversity",
    "startup culture", "flat hierarchy", "move fast",
    "hack days", "hackathon",
]

CULTURE_ENTERPRISE_SIGNALS = [
    "work-life balance", "work life balance", "unlimited pto",
    "generous pto", "parental leave", "401k match", "pension",
    "health insurance", "dental", "vision",
    "mentorship", "learning budget", "education stipend",
    "employee resource groups", "erg", "professional development",
    "wellness", "mental health", "sabbatical",
    "inclusive", "diversity", "dei", "belonging",
    "collaborative", "team-oriented", "cross-functional",
    "internal mobility", "career development", "tuition reimbursement",
    "conferences", "speaker", "training",
]

# ── Company tier baselines ────────────────────────────────────────────────
#
# Floor scores keyed by company_type (from classify_company()).
# The keyword-based score is blended via max(keyword_score, baseline).

TIER_BASELINES: dict[str, dict[str, float]] = {
    # technical: high-bar engineering orgs get a floor even when JDs are generic
    # leadership: known career-ladder / scope opportunities at each tier
    "FAANG+":         {"trajectory": 80, "comp": 85, "culture": 60, "platform": 30, "technical": 55, "leadership": 45},
    "Big Tech":       {"trajectory": 70, "comp": 75, "culture": 55, "platform": 25, "technical": 50, "leadership": 40},
    "Elite Startup":  {"trajectory": 75, "comp": 70, "culture": 55, "platform": 45, "technical": 45, "leadership": 45},
    "Growth Stage":   {"trajectory": 60, "comp": 50, "culture": 45, "platform": 40, "technical": 35, "leadership": 30},
    "Early Startup":  {"trajectory": 40, "comp": 35, "culture": 40, "platform": 55, "technical": 30, "leadership": 25},
    "Midsize":        {"trajectory": 45, "comp": 50, "culture": 45, "platform": 20, "technical": 30, "leadership": 20},
    "Enterprise":     {"trajectory": 55, "comp": 60, "culture": 50, "platform": 15, "technical": 40, "leadership": 30},
    "Unknown":        {"trajectory": 25, "comp": 25, "culture": 25, "platform": 15, "technical": 20, "leadership": 15},
}

# ── Career progression ────────────────────────────────────────────────────

LEVEL_MAP: dict[str, float] = {
    # Universal seniority tiers
    "intern": 0, "junior": 1, "associate": 1, "entry": 1,
    "mid": 2, "senior": 3, "sr": 3,
    "staff": 4, "principal": 5, "distinguished": 6,
    "lead": 3.5, "tech lead": 3.5,
    "manager": 4, "senior manager": 5,
    "director": 6, "senior director": 7,
    "vp": 8, "svp": 9, "evp": 9,
    "head of": 6, "founding": 4,
    # Engineering-specific
    "engineering manager": 4, "senior engineering manager": 5,
    "cto": 10, "cio": 10,
    # Product / Design
    "product manager": 4, "senior product manager": 5, "group product manager": 6,
    "cpo": 10, "design manager": 4, "design director": 6, "creative director": 6,
    # Sales / Business
    "account executive": 2, "senior account executive": 3,
    "sales manager": 4, "sales director": 6, "cro": 10,
    "business development": 2, "partner": 5,
    # Marketing
    "marketing manager": 4, "marketing director": 6, "cmo": 10,
    "brand manager": 4, "growth manager": 4,
    # Operations / HR / Finance
    "coordinator": 1, "specialist": 2, "analyst": 2, "senior analyst": 3,
    "operations manager": 4, "program manager": 4,
    "coo": 10, "cfo": 10, "chro": 10,
    # Healthcare
    "nurse": 2, "charge nurse": 3, "nurse manager": 4, "nurse director": 6,
    "physician": 5, "attending": 5, "chief medical officer": 10,
    # Education
    "teacher": 2, "professor": 4, "department chair": 6, "dean": 8,
    # General
    "consultant": 3, "advisor": 3, "fellow": 5,
    "chief executive": 7, "executive officer": 7,
    "executive director": 6, "executive vice president": 9,
    "sales executive": 3, "executive assistant": 1,
    "chief": 10, "president": 10, "ceo": 10,
}

SCOPE_KEYWORDS = [
    "build the team", "own the roadmap", "founding", "head of",
    "from scratch", "0 to 1", "define strategy", "budget", "p&l",
    "cross-functional", "org design", "build out the team",
    "strategic planning", "executive leadership", "department",
    "oversee", "full ownership", "end to end",
]

MGMT_SIGNALS = [
    "manager", "director", "vp", "cto", "cmo", "cfo", "coo",
    "head of", "chief", "president", "superintendent", "dean",
]
