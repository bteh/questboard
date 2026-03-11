# Launchboard

**Your personal AI agent for the job search grind.**

Launchboard searches 5+ job boards, scores listings against your resume across 7 dimensions, generates tailored cover letters and resume tweaks, drafts company research for interview prep, and optionally auto-applies through ATS APIs. The core pipeline, database, and resume handling run locally on your machine.

The job market rewards quality over volume. Launchboard is built on a simple thesis: the best job search tool is one that thinks like a hiring manager, not a spray-and-pray bot.

---

## What It Does Today

**Search** -- Searches 14+ sources in parallel: Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs (via JobSpy), plus Remotive, Arbeitnow, Himalayas, RemoteOK, Jobicy, We Work Remotely, Hacker News Who's Hiring, The Muse, CryptoJobsList, and ATS boards from 100+ companies via Greenhouse, Lever, and Ashby APIs. YC Work at a Startup scraper extracts listings from Inertia.js page data. Filters by location preferences. Deduplication is URL-based.

**Score** -- Rates every job on 7 weighted dimensions: technical match (TF-IDF + keywords), leadership signal, compensation potential, platform-building opportunity, company trajectory, culture fit, and career progression. The platform-building dimension (13% weight) specifically rewards startup signals like "greenfield", "0 to 1", "first data hire", and "founding engineer". Works without any LLM. With an LLM connected, scoring becomes context-aware.

**Classify** -- Automatically categorizes companies into 8 tiers (FAANG+, Big Tech, Elite Startup, Growth Stage, Early Startup, Midsize, Enterprise, Unknown) using known-company lists (including 50+ VC-backed startups like OpenAI, Anthropic, Stripe, dbt Labs, Vercel), funding stage heuristics, and employee count data. Filter your dashboard by tier to focus on the company stage that fits you.

**Enhance** -- For top-scoring jobs, generates tailored resume bullet tweaks, cover letters grounded in your resume plus the job description, and company-intel drafts. These LLM-generated materials are starting points, not verified facts.

**Auto-Apply** -- Submits applications through Greenhouse and Lever endpoints for STRONG_APPLY jobs when those ATS links are detected. Opt-in only, dry-run by default, with a hard cap per run.

**Track** -- Every job flows into a SQLite database with 50+ fields. Track status from "found" through "offer." Export to CSV. Full analytics dashboard with score distributions, pipeline funnels, and company breakdowns.

---

## Architecture

```
                    YAML Profile
                        |
                        v
               +------------------+
               |    Pipeline      |  search -> score -> enhance -> save -> auto-apply
               +------------------+
              /         |          \
             v          v           v
        +--------+  +--------+  +---------+
        | Search |  | Score  |  | Enhance |
        +--------+  +--------+  +---------+
        | JobSpy |  | TF-IDF |  | LLM     |  <-- LLM is optional
        | YC     |  | KW     |  | Client  |      at every stage
        +--------+  +--------+  +---------+
                        |
                        v
               +------------------+
               |    SQLite DB     |  ApplicationRecord (50+ columns)
               +------------------+
                   /          \
                  v            v
      +----------------+  +------------------+
      | FastAPI Backend |  | React Frontend   |
      | REST API        |  | TanStack Router  |
      | SSE streaming   |  | Tailwind CSS     |
      +----------------+  +------------------+
```

There are two UI options:
- **Web UI (recommended):** FastAPI backend + React frontend. Run with `make dev`.
- **Streamlit UI (legacy):** Single-file dashboard. Run with `streamlit run app.py`.

**Key design decision:** LLM features are additive, never required. Search works with zero API keys. Resume-based scoring requires a PDF resume. AI features unlock progressively as you connect a provider.

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/bteh/launchboard.git
cd launchboard
make setup          # installs Python + Node deps, creates .env

# Add your resume
cp your_resume.pdf knowledge/yourname_resume.pdf

# Create your profile
cp src/job_finder/config/profiles/_template.yaml src/job_finder/config/profiles/yourname.yaml

# Launch the web UI (recommended)
make dev
# Backend: http://localhost:8000   Frontend: http://localhost:5173

# Or launch the legacy Streamlit UI
streamlit run app.py
```

Searching and offline scoring do not require API keys. Resume-based scoring does require a PDF resume in `knowledge/`. LLM-generated cover letters and company research should always be reviewed before you send or rely on them.

## Reliability Boundaries

- Search, offline scoring, tracking, and ATS detection are deterministic local code paths.
- LLM-generated cover letters, resume tweaks, and company research are drafts. Verify company facts, recent news, funding details, and interview-process claims yourself.
- Auto-apply is opt-in and `dry_run: true` by default.
- Multiple profiles are supported for local use, but this is not a shared multi-user product yet. If you and your friends want separate histories and settings, use separate profiles at minimum; separate clones or data directories are safer.

### Connect an LLM (optional, unlocks full AI pipeline)

The fastest free option is Google Gemini:

1. Get an API key at [aistudio.google.com](https://aistudio.google.com) (30 seconds, free tier)
2. In the app, go to **Settings > LLM Provider**
3. Select "Google Gemini", paste your key, click **Save & Test**

Other supported providers (all configurable in Settings):

| Provider | Cost | Notes |
|----------|------|-------|
| Google Gemini | Free (250 req/day) | Recommended free option |
| Groq | Free (1,000 req/day) | Fastest inference |
| OpenRouter | Free (200 req/day) | 27+ free models |
| Cerebras | Free (1M tokens/day) | Ultra-fast |
| SambaNova | Free | Large Llama models |
| Mistral | Free (1B tokens/month) | European provider |
| DeepSeek | Free credits + cheap | Strong reasoning |
| Anthropic API | Pay-per-use | Claude models |
| OpenAI API | Pay-per-use | GPT models |
| Ollama | Free (local) | Run models on your machine |

---

## Profile System

Launchboard uses YAML profiles to customize everything per user. Each profile controls:

- **Target roles and keywords** -- what to search for
- **Scoring weights** -- which dimensions matter most to you
- **Compensation targets** -- salary thresholds for scoring
- **Career baseline** -- your current title/level for progression scoring
- **Location preferences** -- geographic filtering with remote-always-passes logic
- **Auto-apply settings** -- applicant info, ATS preferences, safety controls

```bash
# Create your profile
cp src/job_finder/config/profiles/_template.yaml src/job_finder/config/profiles/yourname.yaml

# Add your profile-specific resume
cp your_resume.pdf knowledge/yourname_resume.pdf
```

Select your profile in the sidebar. The entire pipeline adapts: search queries, scoring weights, prompt templates, and database tagging all key off the active profile.

---

## Scoring Deep Dive

Every job is scored on 7 dimensions, each producing a 0-100 sub-score. The overall score is a weighted sum.

| Dimension | Default Weight | What It Measures |
|-----------|---------------|------------------|
| Technical Skills | 25% | TF-IDF cosine similarity + keyword saturation curve |
| Leadership Signal | 15% | Keywords like "head of", "founding", "own the roadmap" |
| Career Progression | 15% | Title escalation, scope expansion, comp upgrade vs. your baseline |
| Platform Building | 13% | Greenfield, "0 to 1", "build from scratch" signals |
| Comp Potential | 12% | Salary data or inferred from company/level signals |
| Company Trajectory | 10% | Funding, growth, hiring signals |
| Culture Fit | 10% | Remote, modern practices, collaboration signals |

**Recommendations** are derived from the overall score:
- **STRONG_APPLY** (70+) -- Drop everything and apply. Full AI enhancement.
- **APPLY** (55-69) -- Worth pursuing. Resume tweaks generated.
- **MAYBE** (40-54) -- Review manually.
- **SKIP** (<40) -- Likely not a fit.

All thresholds and weights are configurable per profile.

---

## Product Roadmap

### Done

- [x] 14+ source parallel search (JobSpy, Remotive, Arbeitnow, Himalayas, RemoteOK, Jobicy, We Work Remotely, Hacker News, The Muse, CryptoJobsList, Greenhouse, Lever, Ashby, YC Work at a Startup, Workday)
- [x] Plugin-based scraper registry — add a new source with one decorated file
- [x] 7-dimension weighted scoring (TF-IDF + keywords, works offline)
- [x] 10 free LLM provider integrations + live model fetching from provider APIs
- [x] Auto-apply via Greenhouse and Lever APIs (opt-in, dry-run default)
- [x] Resume upload with auto-analysis (extracts skills, roles, career baseline)
- [x] FastAPI backend with SSE streaming + React frontend
- [x] SQLite application tracker with 50+ fields
- [x] 8-tier company classification with 50+ known startups
- [x] Profile-driven config (YAML)

### Next

- [ ] **Interview Prep** -- STAR-format answers from resume + JD
- [ ] **Salary Intelligence** -- Cross-reference comp data, negotiation talking points
- [ ] **Scoring Calibration** -- Feed back outcomes to tune weights
- [ ] **Scheduled Scanning** -- Background search with notifications
- [ ] **Browser Extension** -- Score any job page in-browser

---

## Configuration Reference

### Environment Variables (`.env`)

```bash
LLM_PROVIDER=claude-proxy              # Provider preset name (or empty for no LLM)
LLM_BASE_URL=http://localhost:8317/v1  # Auto-filled from preset
LLM_API_KEY=not-needed                 # Required for anthropic-api, openai-api, gemini
LLM_MODEL=claude-sonnet-4-20250514    # Model identifier
```

### Profile YAML Structure

```yaml
profile:
  name: "Display Name"
  description: "What you're targeting"

target_roles: [...]           # Job titles to search
keyword_searches: [...]       # Technology/specialty keywords
locations: [...]              # "City, ST" or "Remote"

location_preferences:         # Post-search filtering
  filter_enabled: true
  preferred_states: ["CA"]
  preferred_cities: ["Los Angeles"]

keywords:
  technical: [...]            # Your skills (matched against JDs)
  leadership: [...]           # Growth/leadership signals
  platform_building: [...]    # Build-from-scratch signals
  high_comp_signals: [...]    # Company/level comp indicators

scoring:                      # Weights (must sum to 1.0)
  technical_skills: 0.25
  leadership_signal: 0.15
  career_progression: 0.15
  platform_building: 0.13
  comp_potential: 0.12
  company_trajectory: 0.10
  culture_fit: 0.10
  thresholds:
    strong_apply: 70
    apply: 55
    maybe: 40

career_baseline:
  current_title: "Senior Data Engineer"
  current_tc: 200000

compensation:
  min_base: 190000
  target_total_comp: 300000

auto_apply:
  enabled: false
  dry_run: true
  max_applications_per_run: 5
```

---

## Contributing

### Setup

```bash
git clone <your-repo-url>
cd launchboard
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
```

### Project Principles

1. **LLM-optional always.** Every new feature must have a useful non-LLM fallback. Search and basic scoring working offline is non-negotiable.

2. **No frameworks.** The pipeline is plain Python functions and classes. No CrewAI, no LangChain. Keep the dependency tree shallow.

3. **Profile-driven.** New features should read from the YAML profile config. Hard-coded values are bugs.

4. **Graceful degradation.** LLM calls return `None` on failure. Network calls catch exceptions. The pipeline never crashes on a single bad job listing.

5. **Local-first.** SQLite, local PDFs, no cloud storage required. Cloud features are additive, never required.

### Adding a New Job Source

Create one file in `src/job_finder/tools/scrapers/`:

```python
from job_finder.tools.scrapers._registry import register_scraper
from job_finder.tools.scrapers._utils import _get_json, _match_roles

@register_scraper(
    name="myboard",
    display_name="My Board",
    url="https://myboard.com",
    description="Jobs from My Board",
    category="remote",
)
def search_myboard(roles=None, max_results=50, **kwargs) -> list[dict]:
    ...
```

Auto-discovered on import. Metadata flows to the API and frontend automatically.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contributor guide.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Search | python-jobspy, requests, feedparser, BeautifulSoup |
| Scoring | scikit-learn (TF-IDF), custom keyword matching |
| LLM | openai SDK (any compatible endpoint) |
| Database | SQLAlchemy + SQLite |
| Models | Pydantic v2 |
| Backend | FastAPI, uvicorn, SSE streaming |
| Frontend | React 19, TanStack Router, Tailwind CSS, Recharts |
| Legacy UI | Streamlit + Plotly + custom CSS |
| Config | PyYAML, python-dotenv |
| PDF | PyPDF2 |

---

## License

MIT
