# Contributing to Launchboard

Thanks for your interest in improving Launchboard! This guide covers setup, conventions, and how to submit changes.

## Prerequisites

- **Python 3.11+** ([python.org](https://python.org)) — `pyenv` users: `.python-version` handles this
- **Node.js 18+** ([nodejs.org](https://nodejs.org)) — `nvm` users: `.nvmrc` handles this

## Development Setup

```bash
git clone https://github.com/bteh/launchboard.git
cd launchboard
make setup    # creates venv, installs Python + Node deps, copies .env
```

`make setup` creates a `.venv/` virtual environment. All `make` commands use it automatically — you never need to activate it.

## Running

```bash
make dev      # starts backend (localhost:8000) + frontend (localhost:5173)
make backend  # backend only
make frontend # frontend only
```

## Troubleshooting

```bash
make doctor   # checks Python/Node versions, venv, deps, .env, ports
make reset    # recreates venv from scratch if something breaks
```

## Where to Contribute

### Easy wins
- **Add a job source** — One file in `src/job_finder/tools/scrapers/`. Auto-discovered. See below.
- **Frontend polish** — Components, accessibility, responsive design.
- **Bug fixes** — Check open issues.

### Medium
- **Scoring improvements** — New signals, dimension tuning, better keyword lists.
- **LLM prompts** — Improve cover letter quality, scoring accuracy, company research.
- **Tests** — More coverage for scoring, scrapers, and API endpoints.

### Larger efforts
- **Docker Compose** — One-command deployment with bundled Ollama.
- **Auth** — OAuth (Google/GitHub) for the hosted version.
- **PostgreSQL** — Migration from SQLite for concurrent multi-user access.
- **New AI features** — Interview prep, salary intelligence, scoring calibration.

See the Roadmap section in [README.md](README.md) for the full vision.

---

## Adding a New Scraper

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
    # Return list of job dicts with keys:
    # title, company, location, url, description, source, is_remote,
    # salary_min, salary_max, date_posted, company_size
    ...
```

Auto-discovered on import. Metadata flows to the API and frontend automatically.

## Adding a New Scoring Dimension

1. Add the scorer function in `scoring/dimensions.py`
2. Wire it into `scoring/core.py` with its weight
3. Add the weight key to `config/profiles/_template.yaml`
4. Add the column to `ApplicationRecord` in `models/database.py`
5. Add the field to `save_application()`
6. Update `prompts.py` templates
7. Update frontend score display components

## Adding a New LLM Feature

Follow the graceful degradation pattern:

```python
def new_feature(self, ...) -> dict | None:
    if not self.llm or not self.llm.is_configured:
        return None  # always degrade gracefully
    user_msg = TEMPLATE.format(...)
    system_prompt = build_prompt(self.config)
    return self.llm.chat_json(system_prompt, user_msg)
```

---

## Project Principles

1. **AI-enhanced, not AI-dependent.** Every feature must have a useful non-AI fallback. Search and basic scoring offline is non-negotiable.
2. **No frameworks.** Plain Python functions and classes. No CrewAI, no LangChain. Shallow dependency tree.
3. **Profession-agnostic.** Prompts, scoring, and search adapt to any career field via profile config. No tech-specific assumptions.
4. **Graceful degradation.** LLM calls return `None` on failure. Network calls catch exceptions. The pipeline never crashes on a single bad listing.
5. **Local-first.** SQLite, local files, no cloud required. Cloud features are additive.

## Code Style

- **Python 3.10+** with `from __future__ import annotations`
- Type hints on all function signatures (`str | None`, not `Optional`)
- Logging via `logger = logging.getLogger(__name__)`, never `print()` in library code
- `print()` is acceptable in CLI entry points (`main.py`, `setup.py`)
- Snake_case everywhere. Files match their primary class/function.

## Testing

```bash
make test       # Python tests
make typecheck  # TypeScript type checking
```

## Pull Requests

- Keep PRs focused on a single change
- Include a brief description of what and why
- Ensure `pytest` and `tsc --noEmit` pass
- Don't commit `.env`, `data/*.db`, or files in `knowledge/`

## Reporting Issues

Open an issue on GitHub with:
- What you expected
- What happened instead
- Steps to reproduce
- Your OS and Python/Node versions
