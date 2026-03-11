# AGENTS.md -- Launchboard

AI-powered job search agent. Searches 5+ job boards, scores jobs against your resume
using 7-dimension weighted scoring, generates tailored application materials via LLM,
and optionally auto-applies through Greenhouse/Lever APIs.

## Architecture

```
src/job_finder/
  pipeline.py              # 7-stage orchestrator: search -> parse -> score -> optimize -> cover letter -> research -> auto-apply
  llm_client.py            # Unified OpenAI-compatible client (7 provider presets, health check, JSON parsing)
  scorer.py                # TF-IDF + keyword scoring, 7 dimensions, no LLM needed
  company_classifier.py    # 8-tier company classification (FAANG+ through Unknown) + location filtering
  prompts.py               # Templatized system prompts -- build_*_prompt(config) adapts to profile
  main.py                  # CLI entry points (run, search, score)
  config/
    search_config.yaml     # Default config
    profiles/*.yaml        # Per-user profiles (brian.yaml, _template.yaml)
  models/
    database.py            # SQLAlchemy ORM -- ApplicationRecord (50+ columns), SQLite
    schemas.py             # Pydantic models (JobListing, JobScore, ResumeOptimization, CoverLetter, CompanyIntel)
  tools/
    job_search_tool.py     # JobSpy wrapper -- scrapes Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google
    resume_parser_tool.py  # PyPDF2 extraction with profile-aware resume detection
    auto_apply_tool.py     # Greenhouse + Lever API submission, ATS URL detection, dry-run support
    yc_scraper_tool.py     # YC Work at a Startup scraper (embedded JSON + HTML fallback) -- startup pipeline

app.py                     # Streamlit UI -- 5 pages (Dashboard, Run Search, Applications, Analytics, Settings)
components.py              # Reusable UI components (job cards, badges, pipeline steps, activity feed)
assets/style.css           # Custom CSS (Tailwind-inspired design tokens)
```

## Commands

```bash
# Run Streamlit UI
streamlit run app.py

# CLI -- full pipeline
python -m job_finder.main --profile brian

# CLI -- search only
python -m job_finder.main search --profile brian

# Install
pip install -e .
```

## Development Conventions

- **Python 3.10+** with `from __future__ import annotations`
- **Type hints** on all function signatures (use `str | None` union syntax, not `Optional`)
- **Logging**: `logger = logging.getLogger(__name__)` per module, never `print()` in library code
- **Error handling**: return `None` on failure, let callers degrade gracefully -- never raise in LLM/network code
- **Imports**: standard lib -> third-party -> local. Lazy imports for heavy deps
- **Data flow**: functions accept/return `dict` or `list[dict]` -- Pydantic models exist for validation but pipeline uses plain dicts
- **Config**: YAML profiles loaded via `_load_search_config(profile)`. Profile name threads through pipeline/tools/DB
- **Naming**: snake_case everywhere. Files match their primary class/function

## LLM Integration -- Three Tiers

1. **No LLM** (default): `search_jobs()` + `score_job_basic()` work completely offline. TF-IDF + keyword matching provides baseline scoring.

2. **LLM Scoring**: When `llm.is_configured`, `pipeline.score_job_with_ai()` sends resume + JD to LLM. Returns same dict shape as basic scorer.

3. **Full AI Pipeline**: For STRONG_APPLY/APPLY jobs -- generates resume tweaks, cover letters, and company research. All via `llm.chat_json()`.

**Pattern for new LLM features:**
```python
def new_feature(self, ...) -> dict | None:
    if not self.llm or not self.llm.is_configured:
        return None  # always degrade gracefully
    user_msg = TEMPLATE.format(...)
    system_prompt = build_prompt(self.config)  # profile-aware
    return self.llm.chat_json(system_prompt, user_msg)
```

## Scoring System

7 weighted dimensions (must sum to 1.0):
- `technical_skills` (0.25) -- TF-IDF cosine similarity + keyword saturation curve
- `leadership_signal` (0.15) -- leadership keyword detection
- `career_progression` (0.15) -- title level extraction, scope signals, comp upgrade
- `platform_building` (0.13) -- greenfield/build-from-scratch/founding engineer startup signals
- `comp_potential` (0.12) -- salary data or inferred from company/level signals
- `company_trajectory` (0.10) -- funding/growth signals
- `culture_fit` (0.10) -- remote, modern practices, collaboration signals

Recommendations: STRONG_APPLY (>=70), APPLY (>=55), MAYBE (>=40), SKIP (<40). Thresholds configurable per profile.

## Auto-Apply Safety Rules

- Always disabled by default (`enabled: false`)
- `dry_run: true` by default -- logs what would happen without submitting
- Only applies to STRONG_APPLY recommendations
- Only Greenhouse and Lever APIs (LinkedIn flagged as manual-only)
- Requires `applicant_info` in config (first_name, email minimum)
- Capped by `max_applications_per_run` (default: 5)
- DB status updated to "applied" only on successful live submission

## Database

SQLite at `data/job_tracker.db`. `ApplicationRecord` has 50+ columns covering job info, all 7 score
dimensions, company intel JSON, cover letter, resume tweaks, application method, status tracking, and
timestamps. Deduplication by `job_url` (unique constraint). Lightweight migration via `_migrate_db()`
adds missing columns to existing tables.

## Startup & Source Coverage

Job sources: JobSpy (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google) + YC Work at a Startup scraper.
Profile config has `additional_sources` (workatastartup, greenhouse, lever URLs) and `target_companies`
with `startup_criteria` (funding stages, min funding amount, founding role preference). The company
classifier knows 50+ VC-backed startups (OpenAI, Anthropic, Stripe, dbt Labs, Vercel, etc.) and
classifies by funding stage/amount/employee count. Auto-apply detects Greenhouse/Lever from job URLs.

## Key Patterns to Reuse

- **Progress callbacks**: `progress: Callable[[str], None] | None` -- pass `st.progress` or `print`
- **Profile threading**: `profile` parameter flows from CLI/UI -> pipeline -> tools -> database
- **Config-driven prompts**: `build_*_prompt(config)` reads keywords/weights/thresholds from YAML
- **Graceful degradation**: every LLM method returns `None` when unavailable
- **Safe type helpers**: `_safe_str()`, `_safe_float()`, `_safe_bool()` for pandas NaN handling

## Anti-Patterns -- Do NOT

- Add framework dependencies (no CrewAI, LangChain, etc.) -- the pipeline is intentionally framework-free
- Require an LLM for basic functionality -- search and keyword scoring must always work offline
- Use `print()` in library code -- use `logger` and progress callbacks
- Store secrets in YAML profiles -- use `.env` for API keys
- Skip `dry_run` safety -- auto-apply must default to dry-run
- Mutate the scoring weight contract -- always return all 7 dimension scores + recommendation
- Add cloud dependencies -- the system is local-first (SQLite, local PDFs)
- Access `st.session_state` from library code -- keep Streamlit concerns in `app.py` and `components.py`
