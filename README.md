# Launchboard

**AI-powered job search agent.** Upload your resume, tell it what you're looking for, and Launchboard searches 14+ job boards, scores every listing against your background, generates tailored cover letters, and tracks your entire pipeline. Works for any profession.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## How It Works

1. **Upload your resume** — Launchboard extracts your skills, experience, and career level automatically.
2. **Set your preferences** — Target roles, keywords, locations, salary range. Takes 2 minutes.
3. **Search** — Searches 14+ job boards in parallel. AI enriches your search terms so you don't miss relevant postings.
4. **Score** — Every job is rated on 7 dimensions (skills match, compensation, career growth, culture fit, and more). Jobs are ranked into STRONG APPLY, APPLY, MAYBE, and SKIP.
5. **Enhance** — For top matches, generates tailored cover letters, resume tweaks, and company research.
6. **Track** — Full pipeline from "found" to "offer" with analytics dashboard.

---

## Quick Start

**Prerequisites:** Python 3.11+ and Node.js 18+.

```bash
git clone https://github.com/bteh/launchboard.git
cd launchboard
make setup    # installs everything, offers to set up AI automatically
make dev      # opens the web UI
```

That's it. Open [localhost:5173](http://localhost:5173), upload your resume, set your preferences, and search.

`make setup` creates a Python virtual environment, installs all dependencies, and walks you through AI setup (Ollama local or Gemini free). You don't need to activate the venv — all `make` commands handle it.

## Product Direction

As of **April 3, 2026**, Launchboard is moving toward a **desktop-first** product strategy.

That means:

- the open-source/local experience is the primary product
- desktop packaging is the next major milestone
- hosted SaaS remains a later option, not the immediate focus

The rationale and rollout plan are in [docs/desktop-first.md](docs/desktop-first.md).
Release packaging details are in [docs/desktop-release.md](docs/desktop-release.md).
Desktop AI connection policy is in [docs/ai-access.md](docs/ai-access.md).

### Hosted-like local sandbox

If you want local development to behave like the hosted product, use:

```bash
make dev-hosted
```

That starts the backend, worker, and frontend in hosted mode with seeded personas. Each persona has an isolated workspace, resume, and search preferences so you can switch between very different user backgrounds without wiring a real auth provider first.
By default, the sandbox now opens with a blank test-account flow so you can verify the real hosted onboarding path: create an account, upload a resume, and search. Sample personas remain available as an optional QA tool inside that screen.

### Desktop development

Launchboard is moving toward a desktop-first product, and the first desktop scaffold now lives in `frontend/src-tauri`.

For contributors:

```bash
make setup
make desktop-dev
```

Requirements:

- Python 3.11+
- Node 18+
- Rust toolchain via [rustup](https://rustup.rs)

The desktop shell uses Tauri v2 and starts the local Launchboard runtime on `127.0.0.1:8765`. In development it uses your repo `.venv`; for desktop builds, `make setup` now installs PyInstaller so the Python runtime can be packaged as a sidecar.
The packaged sidecar is staged under `.desktop-build/tauri-sidecars`, which keeps build artifacts out of the live `src-tauri` tree and avoids unnecessary dev-shell rebuilds.
Desktop release builds follow your Python architecture on macOS. If you are on Apple Silicon but your `.venv` is an `x86_64` Python under Rosetta, Launchboard will produce an `x86_64` desktop app so the packaged Python sidecar and Tauri shell stay compatible.

For a local packaged build:

```bash
make desktop-build
```

That now verifies the packaged app bundle and sidecar architecture automatically before it succeeds.

To replace the copy in `Applications` with your newest local build:

```bash
make desktop-install
```

That backs up the existing installed app under `.desktop-build/install-backups/` and copies the latest built `Launchboard.app` into `/Applications`.

For a full desktop UX smoke check against the local runtime and desktop web shell:

```bash
npm --prefix frontend run desktop:smoke:install   # one-time browser install
make desktop-smoke
```

The smoke run now exercises first-launch onboarding, resume upload, basic search start, and a runtime restart to verify the local desktop session persists cleanly.
If it fails, traces and screenshots are written to `test-results/desktop-smoke/`.

### Connect AI

Launchboard uses AI to score jobs against your resume, generate cover letters, and research companies. The fastest option:

**Google Gemini (free, 30 seconds, no credit card):**
1. Get a key at [aistudio.google.com](https://aistudio.google.com/apikey)
2. In the app → Settings → paste your key → Connect

**Or run AI locally (completely private):**
```bash
# make setup offers this automatically, or do it manually:
brew install ollama && ollama pull llama3.2:3b
```

All 10 providers are configurable in Settings:

| Provider | Cost | Notes |
|----------|------|-------|
| Google Gemini | Free (250/day) | Recommended — best free model |
| Groq | Free (1,000/day) | Fastest |
| Cerebras | Free | Generous free tier |
| OpenRouter | Free (200/day) | 29 free models |
| Mistral | Free | European provider |
| DeepSeek | Free credits | Strong reasoning |
| SambaNova | Trial credits | Powerful models |
| OpenAI API | Paid | GPT-4o (separate from ChatGPT Plus) |
| Anthropic API | Paid | Claude (separate from Claude Pro) |
| Ollama | Free (local) | Private, runs on your machine |

Any OpenAI-compatible endpoint also works — configure it under **Custom Provider** in Settings.

> **Note:** ChatGPT Plus and Claude Pro/Max are chat subscriptions. They don't include API access for third-party apps. The free options above work great.

### Supported desktop AI paths

Supported today:

- Gemini API key
- OpenAI API key
- Anthropic API key
- Ollama / local models
- your own local OpenAI-compatible endpoint

Not supported today:

- signing into Launchboard with your ChatGPT account
- signing into Launchboard with your Claude account

That distinction is deliberate. Launchboard desktop is local-first, but it still only exposes AI access patterns we can support clearly right now. See [docs/ai-access.md](docs/ai-access.md).

---

## What It Does

**Search** — 14+ sources in parallel: Indeed, Glassdoor, ZipRecruiter, Google Jobs, Remotive, Arbeitnow, Himalayas, RemoteOK, We Work Remotely, Hacker News Who's Hiring, The Muse, CryptoJobsList, YC Work at a Startup, plus direct ATS board scraping via Greenhouse, Lever, Ashby, and Workday APIs (add companies through your watchlist). LinkedIn is available as an optional source in open-source/local mode if you explicitly enable it, and may break or be blocked at any time. AI-powered role expansion enriches search terms for any profession.

**Score** — 7 weighted dimensions, all configurable per profile:

| Dimension | Default Weight | What It Measures |
|-----------|---------------|------------------|
| Technical Skills | 25% | TF-IDF cosine similarity + keyword matching |
| Leadership Signal | 15% | "head of", "founding", "own the roadmap" |
| Career Progression | 15% | Title escalation, scope, comp upgrade |
| Platform Building | 13% | Greenfield, "0 to 1", "build from scratch" |
| Comp Potential | 12% | Salary data or inferred signals |
| Company Trajectory | 10% | Funding, growth, hiring momentum |
| Culture Fit | 10% | Remote, modern practices, collaboration |

Works without AI (keyword matching). With AI connected, every job gets context-aware scoring.

**Classify** — 8-tier company classification (FAANG+ through Unknown) using funding signals, employee data, and known-company lists. Filter your dashboard by company stage.

**Enhance** — For top-scoring jobs: tailored cover letters, resume bullet tweaks, and company research. LLM-generated — always review before sending.

**Auto-Apply** — Submits through Greenhouse and Lever APIs for STRONG_APPLY jobs. Opt-in, dry-run by default, capped per run.

**Track** — SQLite database with 50+ fields. Status tracking, CSV export, analytics dashboard with score distributions and pipeline funnels.

---

## Architecture

```
                    Upload Resume + Set Preferences
                              |
                              v
                   +--------------------+
                   |     Pipeline       |  search → score → enhance → save
                   +--------------------+
                  /         |            \
                 v          v             v
          +--------+   +--------+   +---------+
          | Search |   | Score  |   | Enhance |
          +--------+   +--------+   +---------+
          | 14+    |   | TF-IDF |   | LLM     |  ← AI is additive,
          | boards |   | + LLM  |   | covers  |    never required
          +--------+   +--------+   +---------+
                           |
                           v
                  +------------------+
                  |    SQLite DB     |  50+ columns per job
                  +------------------+
                     /           \
                    v             v
        +----------------+  +------------------+
        | FastAPI Backend |  | React Frontend   |
        | REST API + SSE  |  | TanStack Router  |
        +----------------+  +------------------+
```

---

## Self-Hosting

### Docker (recommended for deployment)

```bash
docker compose up
```

Runs the full stack: backend, frontend, and optionally Ollama for local AI. Configure your LLM provider in `.env` before starting.

### Manual

```bash
make setup    # one-time setup
make dev      # start development servers
```

### Environment Variables

```bash
# .env — LLM configuration (set via Settings UI or here)
LLM_PROVIDER=gemini                  # Provider name
LLM_BASE_URL=                        # Auto-filled from provider
LLM_API_KEY=your-api-key-here        # From provider's dashboard
LLM_MODEL=gemini-2.5-flash           # Model identifier
```

### Hosted Public Beta (Later)

Hosted mode now supports:

- Supabase bearer-authenticated users
- Postgres as the hosted system of record
- Supabase Storage-backed resume/file assets
- durable worker-backed search runs with database progress events

Deployment details and env vars are in [docs/hosting.md](docs/hosting.md).
Hosted is still supported as a technical direction, but it is no longer the immediate product priority.

---

## Profile System

YAML profiles customize everything per user: target roles, scoring weights, compensation targets, location preferences, and auto-apply settings.

```bash
# Create your profile from the template
cp src/job_finder/config/profiles/_template.yaml \
   src/job_finder/config/profiles/yourname.yaml
```

Or use the web UI — Settings handles everything without touching YAML.

---

## Roadmap

### Done
- [x] 14-source parallel search with plugin scraper registry
- [x] 7-dimension weighted scoring (works offline, enhanced with AI)
- [x] 10 LLM provider integrations + custom provider support
- [x] AI auto-suggests search params from resume (no manual config needed)
- [x] Auto-apply via Greenhouse and Lever APIs
- [x] Resume upload with automatic skill/role extraction
- [x] FastAPI backend + React frontend with SSE streaming
- [x] Company classification (8 tiers)
- [x] Watchlist-driven ATS scraping (add any company, auto-detects ATS)
- [x] Multi-user workspaces with data isolation
- [x] Hosted mode gating for local-only features
- [x] Profile-driven configuration
- [x] Supabase-backed hosted auth bootstrap (`/api/v1/me`)
- [x] Durable hosted search queue + worker heartbeats
- [x] Alembic migrations for hosted schema management

### Next
- [ ] **Desktop app shell** — Tauri v2 shell around the existing React app
- [ ] **Bundled local runtime** — Package the Python backend as a desktop sidecar
- [ ] **macOS direct download** — Signed and notarized first public desktop release
- [ ] **Desktop updates** — Signed updater artifacts after packaging is stable
- [ ] **Billing** — Stripe or PayPal entitlements for hosted plans
- [ ] **Hosted schedules** — Workspace-scoped scheduled scans through the worker
- [ ] **Interview Prep** — STAR-format answers from resume + job description
- [ ] **Salary Intelligence** — Cross-reference comp data, negotiation points
- [ ] **Scoring Calibration** — Feed back outcomes to tune weights
- [ ] **Browser Extension** — Score any job page inline

### Vision
Launchboard is open source and local-first. The near-term vision is a desktop app where anyone can download Launchboard, keep their resume and AI setup on their own machine, and start searching without hosted SaaS friction. Hosted can still exist later, but desktop is now the primary path.

---

## Contributing

```bash
git clone https://github.com/bteh/launchboard.git
cd launchboard
make setup && make dev
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide. The easiest way to contribute:

- **Add a job source** — One decorated file in `src/job_finder/tools/scrapers/`. Auto-discovered.
- **Improve scoring** — Add signals, tune dimensions, or add new ones.
- **Frontend polish** — Components, UX, accessibility.
- **Bug reports** — Open an issue with steps to reproduce.

Community and repo policies:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [SECURITY.md](SECURITY.md)

### Principles

1. **AI-enhanced, not AI-dependent.** Search and basic scoring always work offline.
2. **No frameworks.** Plain Python, no CrewAI/LangChain. Keep dependencies shallow.
3. **Profession-agnostic.** Works for nurses, marketers, and engineers alike.
4. **Graceful degradation.** LLM calls return `None` on failure. Pipeline never crashes.
5. **Local-first.** SQLite, local files, no cloud required.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Search | python-jobspy, requests, feedparser, BeautifulSoup |
| Scoring | scikit-learn (TF-IDF), custom keyword matching |
| LLM | openai SDK (any compatible endpoint) |
| Database | SQLAlchemy + SQLite (local), Postgres + Alembic (hosted) |
| Backend | FastAPI, uvicorn, SSE streaming |
| Frontend | React 19, TanStack Router, Tailwind CSS, Recharts, Supabase JS |
| Config | PyYAML, python-dotenv, Pydantic v2 |

Desktop packaging target:

- Tauri v2 shell
- Python sidecar runtime

---

## Reliability Boundaries

- Search, offline scoring, tracking, and ATS detection are deterministic local code.
- LLM-generated cover letters, resume tweaks, and company research are drafts. Verify facts yourself.
- Auto-apply is opt-in, `dry_run: true` by default, capped per run.
- Deduplication is URL-based. Cross-board duplicates with different URLs can survive.

---

## License

MIT
