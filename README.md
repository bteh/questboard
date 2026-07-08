# Questboard

**AI-powered job search agent.** Upload your resume, set your target roles, and Questboard searches 14+ job boards, scores every listing against your background, drafts tailored cover letters, and tracks your pipeline — all on your own machine.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![CI](https://github.com/bteh/questboard/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bteh/questboard/actions/workflows/ci.yml)

## Quick start

```bash
git clone https://github.com/bteh/questboard.git
cd questboard
make setup
make dev
```

That's it. Open [localhost:5173](http://localhost:5173), upload your resume, set your roles, search.

`make setup` walks you through optional AI setup (free Gemini key or local Ollama). Search and basic scoring work without AI.

## What it does

- **Searches 14+ sources in parallel** — Indeed, Glassdoor, LinkedIn, Greenhouse / Lever / Ashby ATS boards (preloaded with 150+ active startup slugs), YC Work at a Startup, RemoteOK, Hacker News Who's Hiring, and more
- **Scores every job** across 7 weighted dimensions: skills match, leadership, career progression, comp, platform building, company trajectory, culture fit
- **Drafts cover letters and resume tweaks** for top matches via your LLM
- **Auto-applies** through Greenhouse + Lever APIs (opt-in, dry-run by default, capped per run)
- **Tracks your pipeline** end-to-end — analytics dashboard, status flow, CSV export

Profession-agnostic: works for engineers, nurses, marketers, designers — prompts and scoring keywords adapt via your YAML profile.

## Connect AI (optional)

The fastest free path:

1. Get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Settings → paste it → Connect (30 seconds)

Or run AI locally:

```bash
brew install ollama && ollama pull llama3.2:3b
```

10 providers configurable in Settings (Gemini, Groq, Cerebras, OpenRouter, Mistral, DeepSeek, SambaNova, OpenAI, Anthropic, Ollama). Any OpenAI-compatible endpoint works via Custom Provider. Detail in [docs/ai-access.md](docs/ai-access.md).

> **Heads up:** ChatGPT Plus and Claude Pro are chat-only subscriptions — they don't include API access for third-party apps. Use the free options above.

## Self-hosting

```bash
docker compose up
```

Runs the full stack with optional bundled Ollama. Configure your LLM in `.env`. Hosted-deployment detail in [docs/hosting.md](docs/hosting.md).

## Desktop app

Questboard is moving toward a desktop-first experience (Tauri shell + Python sidecar runtime). Build locally:

```bash
make desktop-dev      # dev mode against your local repo .venv
make desktop-build    # packaged macOS bundle (verifies bundle + sidecar arch)
```

Requires Python 3.11+, Node 18+, and the Rust toolchain via [rustup](https://rustup.rs). Background in [docs/desktop-first.md](docs/desktop-first.md), packaging in [docs/desktop-release.md](docs/desktop-release.md).

## Project layout

```
src/job_finder/    # pipeline, scrapers, scoring, prompts, LLM client
backend/           # FastAPI REST + SSE
frontend/          # React 19 + TanStack Router + Tailwind
docs/              # design docs (desktop-first, hosting, ai-access, etc.)
```

Architecture and conventions: [CLAUDE.md](CLAUDE.md). Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md).

## Reliability boundaries

- **Local code paths are deterministic** — search, offline scoring, ATS detection, persistence
- **LLM outputs are drafts** — cover letters, resume tweaks, and company research are not web-grounded; verify factual claims yourself
- **Auto-apply is opt-in** — `dry_run: true` by default, only Greenhouse/Lever, only STRONG_APPLY jobs, capped per run
- **Dedup is URL-keyed** — exact duplicates are removed; fuzzy cross-board duplicates with different URLs can survive

## Contributing

We work via pull requests on `main`:

```bash
git checkout -b feat/my-thing
# … hack, commit small atomic changes …
gh pr create --fill
```

CODEOWNERS auto-requests review from maintainers. CI must be green and the PR needs 1 approval before merge. Full workflow + setup in [CONTRIBUTING.md](CONTRIBUTING.md).

**Project principles:**
1. **AI-enhanced, not AI-dependent** — offline search and scoring always work
2. **No heavy frameworks** — plain Python, shallow dependency tree (no CrewAI, no LangChain)
3. **Profession-agnostic** — adapts to any career field via profile YAML
4. **Graceful degradation** — LLM calls return `None` on failure, pipeline never crashes
5. **Local-first** — SQLite, local files, no cloud required

## License

[MIT](LICENSE)
