# CLAUDE.md -- Questboard

Local opportunity radar with two workflows: Find Work for career opportunities and
Side Quests for paid studies, gigs, events, grants, bonuses, and other non-career
opportunities. Questboard owns source discovery, freshness, hard filters, receipts,
and local workflow memory. A user's Codex, Claude Code, or compatible MCP client may
perform resume reasoning; Questboard does not provide AI credits. The product contract
is PRODUCT.md and docs/local-agent-product.md.

## Architecture

```
src/job_finder/
  pipeline.py              # source/search pipeline; legacy scoring and drafting remain compatibility paths
  llm_client.py            # Unified OpenAI-compatible client (10 provider presets, health check, JSON parsing)
  scorer.py                # TF-IDF + keyword scoring, 7 dimensions, no LLM needed
  company_classifier.py    # 8-tier company classification (FAANG+ through Unknown) + location filtering
  prompts.py               # Templatized system prompts -- build_*_prompt(config) adapts to any profession
  main.py                  # CLI entry points (run, search, score)
  config/
    search_config.yaml     # Default config
    profiles/*.yaml        # Per-user profiles (default.yaml, _template.yaml)
  models/
    database.py            # SQLAlchemy ORM -- ApplicationRecord (50+ columns), SQLite
    schemas.py             # Pydantic models (JobListing, JobScore, ResumeOptimization, CoverLetter, CompanyIntel)
  scoring/
    core.py                # Scoring orchestrator -- blends keyword + company baselines
    dimensions.py          # Individual dimension scorers (technical, leadership, comp, etc.)
    helpers.py             # TF-IDF, keyword scoring, salary scoring utilities
    signals.py             # Keyword lists, tier baselines, level maps (fallback defaults)
    company_intel.py       # LLM-powered per-company baseline generation
  tools/
    job_search_tool.py     # JobSpy wrapper -- scrapes Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google
    resume_parser_tool.py  # PyPDF2 extraction with profile-aware resume detection
    auto_apply_tool.py     # application kits: ATS URL detection + prefilled field maps; never transmits
    scrapers/              # Plugin registry -- each scraper is one decorated file
      _registry.py         # @register_scraper decorator, ScraperMeta, run_scrapers()
      _utils.py            # Shared helpers (_get_json, _match_roles, _parse_salary, etc.)
      *.py                 # 14 scraper plugins (greenhouse, lever, ashby, workday, remotive, etc.)

backend/
  app/
    main.py                # FastAPI application entry point
    local_mcp.py           # local stdio MCP entry point; never constructs or funds an LLM
    api/                   # REST endpoints (search, applications, settings, analytics, scrapers, etc.)
    schemas/               # Pydantic request/response models
    services/              # Shared business logic, including local_agent_service.py

frontend/
  src/
    routes/                # TanStack Router pages -- kept THIN (data wiring + composition)
    features/              # feature modules (shell/, board/) -- new UI work starts here
    components/            # legacy pre-convention components; migrate on touch
    api/                   # Typed API client functions
    hooks/                 # Custom React hooks (useBoardSummary, useApplications, etc.)
    utils/                 # Constants, helpers

packages/
  kinds/                   # quest-kind taxonomy registry (kinds.json, single source of truth
                           # for TS AND Python -- see docs/adding-a-source.md)
  ui/                      # @questboard/ui trade-paper design system (Poster, KindStamp, ...)
```

Conventions for all of this live in docs/architecture.md.

## Commands

```bash
# Run the web UI (recommended)
make dev
# Backend: http://localhost:8000   Frontend: http://localhost:5173

# CLI -- full pipeline
python -m job_finder.main --profile default

# CLI -- search only
python -m job_finder.main search --profile default

# Install
make setup              # installs Python + Node deps, creates .env

# Connect the local MCP server to installed user-owned agents
make agent-install

# Tests
pytest tests/
cd frontend && pnpm run typecheck
cd frontend && pnpm run test   # vitest unit tests
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

## Agent and AI boundary

1. **Core product:** source discovery, filtering, browsing, persistence, source health, and tracking work without a model.
2. **Primary reasoning path:** `backend/app/local_mcp.py` exposes grounded local tools. The connected user-owned client performs optional resume analysis and ranking.
3. **Resume access:** `get_career_preferences` never returns raw text. `read_resume_for_matching` is a separate consent-gated tool. Side Quest tools never read the resume.
4. **Legacy compatibility:** BYO API and Ollama scoring/drafting remain in the pipeline. Do not make them the first-run dependency or add new Questboard-funded inference.
5. **No external action:** no MCP, REST, or pipeline path may submit, message, register, purchase, or transact.

## Reliability Boundaries

- Offline search, scoring, persistence, and ATS detection are deterministic local code paths.
- LLM outputs are drafts. Cover letters and company research are not grounded by web browsing in the current pipeline, so factual company claims must be verified manually.
- Deduplication is currently keyed to job URLs; exact duplicates are removed reliably, but cross-board duplicates with different URLs can survive.

**Pattern for new LLM features:**
```python
def new_feature(self, ...) -> dict | None:
    if not self.llm or not self.llm.is_configured:
        return None  # always degrade gracefully
    user_msg = TEMPLATE.format(...)
    system_prompt = build_prompt(self.config)  # profile-aware
    return self.llm.chat_json(system_prompt, user_msg)
```

## Legacy scoring system

The seven-dimension score remains for compatibility. It is not the MCP product's
fit contract and must not be presented as proof that a role matches a resume.
MCP search returns retrieval provenance only; the connected agent maps posting
requirements to resume evidence and owns the final fit label.

7 weighted dimensions (must sum to 1.0):
- `technical_skills` (0.25) -- TF-IDF cosine similarity + keyword saturation curve
- `leadership_signal` (0.15) -- leadership keyword detection
- `career_progression` (0.15) -- title level extraction, scope signals, comp upgrade
- `platform_building` (0.13) -- greenfield/build-from-scratch signals
- `comp_potential` (0.12) -- salary data or inferred from company/level signals
- `company_trajectory` (0.10) -- funding/growth signals
- `culture_fit` (0.10) -- remote, modern practices, collaboration signals

All dimensions, keywords, and signals are profile-configurable. Non-tech profiles (nursing, marketing, etc.)
provide domain-specific keywords via YAML. Prompts are profession-agnostic -- they adapt to any field.

Recommendations: STRONG_APPLY (>=70), APPLY (>=55), MAYBE (>=40), SKIP (<40). Thresholds configurable per profile.

## Post-Search Filtering Pipeline

After search, jobs pass through 5 filters in order:
1. **Deduplication** -- URL-based cross-source dedup, keeps richest record
2. **Location filter** -- Matches preferred states/cities; remote passes only when its stated country scope is compatible
3. **Salary filter** -- Hard floor at 70% of `min_base` (keeps jobs with unknown salary)
4. **Level filter** -- Rejects jobs 2+ levels above/below current title
5. **Role relevance filter** -- Uses `_match_roles()` to reject titles that don't match target roles (catches JobSpy noise like "Software Engineer" appearing in nurse searches)
6. **Staffing agency filter** -- Removes known staffing/recruitment agencies

Each filter also purges existing DB records that no longer match.

## Application Kits (prefill-only)

Questboard never transmits an application; the human sends it. The full
argument is docs/anti-slop.md; the code shape is `auto_apply_tool.py`,
which contains no submission path at all (no requests import).

- Kits prepare only for STRONG_APPLY recommendations, opt-in (`auto_apply.enabled: false` by default)
- ATS detection + prefilled field maps for Greenhouse and Lever; LinkedIn kits carry materials only
- Requires `applicant_info` in config (first_name, email minimum)
- DB status becomes "applied" only when the USER marks it after sending; no code path may set it

## Database

SQLite at `data/job_tracker.db`. `ApplicationRecord` has 50+ columns covering job info, all 7 score
dimensions, company intel JSON, cover letter, resume tweaks, application method, status tracking, and
timestamps. Deduplication by `job_url` (unique constraint). Lightweight migration via `_migrate_db()`
adds missing columns to existing tables.

## Source Coverage

**JobSpy**: supports Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, but the
default board set is **Indeed + LinkedIn** only -- both return live results from a
residential IP. Glassdoor (400 "location not parsed"), ZipRecruiter (Cloudflare 403),
and Google (CAPTCHA) are disabled because they fail from a local IP and return nothing.
A per-board circuit breaker (`tools/job_search_tool.py`) skips a board after a *burst*
of errors (threshold within a rolling window, not lifetime), so transient hiccups on
one board don't black out a run -- run with >=2 working boards so an open circuit on
one still leaves results.

**Plugin scrapers** (`src/job_finder/tools/scrapers/`, auto-discovered on import): career
sources (Remotive, Himalayas, We Work Remotely, HN Who's Hiring, RemoteOK, CryptoJobsList,
Getro, Consider, Arbeitnow, The Muse, YC Work at a Startup, plus ATS scrapers for Greenhouse,
Lever, Ashby, and Workday driven by user watchlist) and quest-kind sources (focus groups,
casting, paid research, bank bonuses, sitting). **Reddit is research-only, never board
content** (curation verdict 2026-07-10): the three subreddit scrapers carry
`research_only=True` and no sweep or refresh runs them; they share `_reddit.py` as research
tooling. The per-kind lineup, the curation verdict, research verdicts, and the
declined-with-reasons list live in `docs/source-coverage.md`. Adding a scraper = one
decorated file with a `kind` id validated at import; every run lands in `scrape_runs` and
is judged by `GET /api/v1/scrapers/health`.

## Key Patterns to Reuse

- **Progress callbacks**: `progress: Callable[[str], None] | None` -- pass a callback or `print`
- **Profile threading**: `profile` parameter flows from CLI/UI -> pipeline -> tools -> database
- **Config-driven prompts**: `build_*_prompt(config)` reads keywords/weights/thresholds from YAML
- **Graceful degradation**: every LLM method returns `None` when unavailable
- **Safe type helpers**: `_safe_str()`, `_safe_float()`, `_safe_bool()` for pandas NaN handling

## Anti-Patterns -- Do NOT

- Add framework dependencies (no CrewAI, LangChain, etc.) -- the pipeline is intentionally framework-free
- Require an LLM for basic functionality -- search and keyword scoring must always work offline
- Add Questboard-funded inference, AI-credit accounting, hosted resume ranking, or remote MCP auth to the local-agent branch
- Treat retrieval order, a legacy score, or source freshness as a resume-fit verdict
- Read a resume for Side Quest matching unless the user explicitly asks
- Use `print()` in library code -- use `logger` and progress callbacks
- Store secrets in YAML profiles -- use `.env` for API keys
- Add any code path that transmits an application -- kits prefill, the human sends (docs/anti-slop.md)
- Mutate the scoring weight contract -- always return all 7 dimension scores + recommendation
- Add cloud dependencies -- the system is local-first (SQLite, local PDFs)
- Mix frontend/backend concerns -- keep React in `frontend/`, FastAPI in `backend/`, pipeline in `src/`
