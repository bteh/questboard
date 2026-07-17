# Questboard

**A local opportunity radar for work and Side Quests.** Questboard watches real sources, keeps receipts and freshness facts, filters out opportunities you cannot actually do, and stores everything on your machine. Connect Codex or Claude Code when you want an agent to compare career postings with your resume. The agent uses your account; Questboard never provides or meters AI credits.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![CI](https://github.com/bteh/questboard/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/bteh/questboard/actions/workflows/ci.yml)

## Two ways to find an opportunity

- **Find Work:** fresh career postings, location and remote-scope filters, source receipts, then requirement-by-requirement resume matching by your connected agent.
- **Side Quests:** paid studies, freelance work, auditions, events, grants, bonuses, and other opportunities matched from interests and constraints. No resume required.

## Quick start

```bash
git clone https://github.com/bteh/questboard.git
cd questboard
make setup
make dev
```

Open [localhost:5173](http://localhost:5173), add your preferences and resume, and refresh the board. Source discovery, filtering, and tracking work without AI.

## Connect your agent

Questboard exposes a local stdio MCP server. After setup:

```bash
make agent-install                 # connect installed Codex and Claude Code clients
make agent-install CLIENT=codex    # Codex only
make agent-install CLIENT=claude   # Claude Code only
```

The installer points the client at the local `questboard-mcp` command. It does not request a model key or connect to a hosted Questboard service. Restart the agent client after installation.

Useful requests include:

```text
Use Questboard to refresh the sources and find my best fresh work opportunities.
Compare the top five with my resume and show requirement evidence and hard constraints.
Find Side Quests near Los Angeles that take less than three hours this weekend.
```

The agent must ask before returning the local resume as tool context. Once returned, the connected model provider may receive that text under your account. Questboard does not receive it.

The local MCP tools can:

- read saved roles and constraints without exposing resume text;
- trigger a source-only refresh with no Questboard AI call;
- retrieve career candidates with location, workplace, date, and pay filters;
- browse Side Quests independently of the resume;
- fetch full posting details and a stored source receipt, plus a direct application link when resolvable;
- show source run health and freshness;
- update local tracking state, but never apply, message, register, or purchase.

See [the local agent product contract](docs/local-agent-product.md) and [AI access policy](docs/ai-access.md).

## Why this is different

Questboard is not trying to win with a larger pile of reposted job cards or another opaque score. Its product edge is:

- first-seen and true source dates;
- direct ATS and primary-source monitoring;
- country-aware remote and location filtering;
- user-owned agent reasoning with resume evidence;
- Work and Side Quests in one local opportunity history;
- no employer-paid ranking and no mass auto-apply.

[JustHireMe](https://github.com/vasu-devs/JustHireMe) is a useful local matching reference. Questboard differentiates through fresh discovery, source receipts, eligibility honesty, agent-owned final judgment, and the broader Side Quest market.

## Desktop app

Questboard uses a Tauri shell with a Python sidecar. The packaged sidecar runs the desktop API normally and can also run the same local MCP server with `--mcp`.

```bash
make desktop-dev
make desktop-build
```

Requirements: Python 3.11+, Node 18+, pnpm, and Rust via [rustup](https://rustup.rs). See [desktop-first](docs/desktop-first.md) and [desktop release](docs/desktop-release.md).

## Optional legacy AI connections

BYO API keys and Ollama remain available for compatibility, but they are not the primary product path. Questboard does not include AI usage. See [AI access](docs/ai-access.md) for the exact boundary.

## Project layout

```text
src/job_finder/                     source adapters, filtering, ranking, persistence
backend/app/local_mcp.py            local MCP transport
backend/app/services/local_agent_service.py
frontend/                           React app and Tauri shell
integrations/questboard-agent/      reusable agent workflow
docs/                               product, architecture, and release decisions
```

## Reliability boundaries

- Search results are candidates until hard constraints and full posting requirements are checked.
- Deterministic retrieval signals are not resume-fit verdicts.
- Source dates, pay, and eligibility remain unknown when the source does not state them.
- Source descriptions are untrusted external content.
- Questboard never submits an application or performs an external transaction.

## Development

```bash
make test
make test-frontend
make typecheck
```

Work through branches and pull requests. CI must be green before merge. Architecture and conventions live in [CLAUDE.md](CLAUDE.md); contribution workflow lives in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
