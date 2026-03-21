.PHONY: help setup dev backend frontend search clean docker doctor

# ── Venv detection ────────────────────────────────────────────────────
# All Python commands run through the venv. `make setup` creates it.
PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── First-time setup ───────────────────────────────────────────────────

setup: ## First-time setup (creates venv, installs deps, sets up AI)
	@echo "\n  Launchboard — Setup\n"
	@echo "  [1/6] Checking Python version..."
	@python3 -c "import sys; assert sys.version_info >= (3,11), f'Python 3.11+ required, got {sys.version}'" 2>/dev/null || \
		(echo "  ERROR: Python 3.11+ required. Install from https://python.org" && exit 1)
	@echo "  [2/6] Creating virtual environment..."
	@test -d .venv || python3 -m venv .venv
	@echo "  [3/6] Installing Python dependencies..."
	@$(PIP) install -e . -q
	@$(PIP) install -e ./backend -q
	@echo "  [4/6] Installing frontend dependencies..."
	@cd frontend && npm install --silent
	@echo "  [5/6] Creating directories and config..."
	@mkdir -p data knowledge
	@test -f .env || cp .env.example .env
	@echo "  [6/6] Setting up AI..."
	@bash scripts/setup-ai.sh
	@echo ""
	@echo "  Setup complete! Run 'make dev' to start."
	@echo ""

install: ## Install all dependencies (Python + Node)
	$(PIP) install -e .
	$(PIP) install -e ./backend
	cd frontend && npm install

setup-ai: ## Set up AI (install Ollama + download model)
	@bash scripts/setup-ai.sh

# ── Development ────────────────────────────────────────────────────────

dev: .venv ## Start backend + frontend for development
	@echo "\n  Starting Launchboard...\n"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:5173"
	@echo "  Press Ctrl+C to stop\n"
	@trap 'kill 0' EXIT; \
		cd backend && PYTHONPATH=../src $(CURDIR)/$(PYTHON) -m uvicorn app.main:app --reload --port 8000 & \
		cd frontend && npm run dev & \
		wait

backend: .venv ## Start only the backend (FastAPI)
	cd backend && PYTHONPATH=../src $(CURDIR)/$(PYTHON) -m uvicorn app.main:app --reload --port 8000

frontend: ## Start only the frontend (Vite)
	cd frontend && npm run dev

# Fail fast if venv is missing
.venv:
	@echo "  Error: Virtual environment not found. Run 'make setup' first." && exit 1

# ── CLI Commands ───────────────────────────────────────────────────────

search: .venv ## Run job search (CLI, no UI needed)
	$(PYTHON) -m job_finder.main search $(if $(PROFILE),--profile $(PROFILE))

score: .venv ## Search + score jobs against resume
	$(PYTHON) -m job_finder.main score $(if $(PROFILE),--profile $(PROFILE))

run: .venv ## Full pipeline: search + score + AI enhance
	$(PYTHON) -m job_finder.main $(if $(PROFILE),--profile $(PROFILE))

# ── Testing ───────────────────────────────────────────────────────────

test: .venv ## Run Python tests
	$(PYTHON) -m pytest tests/

typecheck: ## Run TypeScript type checking
	cd frontend && npx tsc --noEmit

# ── Docker ─────────────────────────────────────────────────────────────

docker: ## Start everything with Docker Compose
	docker compose up --build

docker-down: ## Stop Docker services
	docker compose down

# ── Diagnostics ────────────────────────────────────────────────────────

doctor: ## Check your dev environment for common issues
	@echo "\n  Launchboard — Doctor\n"
	@failed=0; \
	printf "  Python:         "; \
	if .venv/bin/python --version 2>/dev/null | sed 's/Python //'; then \
		true; \
	elif python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null; then \
		true; \
	else \
		echo "MISSING — install Python 3.11+ from https://python.org"; failed=1; \
	fi; \
	printf "  Node:           "; \
	if node -v 2>/dev/null; then \
		true; \
	else \
		echo "MISSING — install Node 18+ from https://nodejs.org"; failed=1; \
	fi; \
	printf "  .venv:          "; \
	if test -d .venv && .venv/bin/python -c "" 2>/dev/null; then \
		echo "ok"; \
	else \
		echo "MISSING — run 'make setup'"; failed=1; \
	fi; \
	printf "  Dependencies:   "; \
	if .venv/bin/python -c "import uvicorn, fastapi, sqlalchemy" 2>/dev/null; then \
		echo "ok"; \
	else \
		echo "INCOMPLETE — run 'make setup' (or 'make reset' to start fresh)"; failed=1; \
	fi; \
	printf "  node_modules:   "; \
	if test -d frontend/node_modules; then \
		echo "ok"; \
	else \
		echo "MISSING — run 'cd frontend && npm install'"; failed=1; \
	fi; \
	printf "  .env:           "; \
	if test -f .env; then \
		echo "ok"; \
	else \
		echo "MISSING — run 'cp .env.example .env'"; failed=1; \
	fi; \
	printf "  Ollama:         "; \
	if command -v ollama >/dev/null 2>&1; then \
		if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then \
			echo "running"; \
		else \
			echo "installed (not running — start with 'ollama serve')"; \
		fi; \
	else \
		echo "not installed — run 'make setup-ai' for AI features"; \
	fi; \
	printf "  Port 8000:      "; \
	if lsof -i :8000 >/dev/null 2>&1; then echo "IN USE"; else echo "available"; fi; \
	printf "  Port 5173:      "; \
	if lsof -i :5173 >/dev/null 2>&1; then echo "IN USE"; else echo "available"; fi; \
	echo ""; \
	if [ $$failed -eq 1 ]; then \
		echo "  Some checks failed. Run 'make setup' to fix most issues.\n"; \
		exit 1; \
	else \
		echo "  All good! Run 'make dev' to start.\n"; \
	fi

# ── Utilities ──────────────────────────────────────────────────────────

clean: ## Remove generated files (DB, caches, node_modules)
	rm -rf data/*.db
	rm -rf src/job_finder/output/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

reset: ## Full reset (removes venv + node_modules, then re-runs setup)
	rm -rf .venv frontend/node_modules
	$(MAKE) setup
