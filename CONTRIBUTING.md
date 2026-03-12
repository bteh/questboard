# Contributing to Launchboard

Thanks for your interest in improving Launchboard! This guide covers how to set up a development environment, follow project conventions, and submit changes.

## Development Setup

```bash
git clone https://github.com/bteh/launchboard.git
cd launchboard
make setup              # installs Python + Node deps, creates .env

# Or manually:
python -m venv .venv && source .venv/bin/activate
pip install -e .
cd frontend && npm install && cd ..
pip install -e backend/
cp .env.example .env
```

## Running

```bash
# Web UI (recommended)
make dev
# Backend: http://localhost:8000   Frontend: http://localhost:5173

# CLI
python -m job_finder.main --profile default
```

## Project Principles

1. **LLM-optional always.** Every new feature must have a useful non-LLM fallback. Search and basic scoring working offline is non-negotiable.

2. **No frameworks.** The pipeline is plain Python functions and classes. No CrewAI, no LangChain. Keep the dependency tree shallow.

3. **Profile-driven.** New features should read from the YAML profile config. Hard-coded values are bugs.

4. **Profession-agnostic.** Prompts, scoring, and search terms adapt to any career field via profile config. No tech-specific assumptions.

5. **Graceful degradation.** LLM calls return `None` on failure. Network calls catch exceptions. The pipeline never crashes on a single bad job listing.

6. **Local-first.** SQLite, local PDFs, no cloud storage required.

## Code Style

- **Python 3.10+** with `from __future__ import annotations`
- Type hints on all function signatures (use `str | None`, not `Optional`)
- Logging via `logger = logging.getLogger(__name__)`, never `print()` in library code
- `print()` is acceptable in CLI entry points (`main.py`, `setup.py`)
- Snake_case everywhere. Files match their primary class/function.

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

Auto-discovered on import. Metadata flows to backend API. Frontend picks it up dynamically.

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

## Testing

```bash
# Run tests
pytest tests/

# Type check frontend
cd frontend && npm run typecheck
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
- Your OS and Python version
