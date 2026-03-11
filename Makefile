.PHONY: help setup dev backend frontend search clean docker

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ── First-time setup ───────────────────────────────────────────────────

setup: ## Interactive first-time setup (creates profile, checks deps)
	@echo "\n  Launchboard — Setup\n"
	@python3 -c "import sys; assert sys.version_info >= (3,11), f'Python 3.11+ required, got {sys.version}'" 2>/dev/null || \
		(echo "  ERROR: Python 3.11+ required" && exit 1)
	@echo "  [1/4] Installing Python dependencies..."
	@pip install -e . -q
	@pip install -e ./backend -q
	@echo "  [2/4] Installing frontend dependencies..."
	@cd frontend && npm install --silent
	@echo "  [3/4] Creating directories..."
	@mkdir -p data knowledge
	@echo "  [4/4] Checking environment..."
	@test -f .env || cp .env.example .env
	@echo ""
	@echo "  Setup complete! Next steps:"
	@echo ""
	@echo "    1. Add your resume:  cp ~/resume.pdf knowledge/default_resume.pdf"
	@echo "    2. (Optional) Set up LLM:  edit .env"
	@echo "    3. Start the app:  make dev"
	@echo ""

install: ## Install all dependencies (Python + Node)
	pip install -e .
	pip install -e ./backend
	cd frontend && npm install

# ── Development ────────────────────────────────────────────────────────

dev: ## Start backend + frontend for development
	@echo "\n  Starting Launchboard...\n"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:5173"
	@echo "  Press Ctrl+C to stop\n"
	@trap 'kill 0' EXIT; \
		cd backend && PYTHONPATH=../src uvicorn app.main:app --reload --port 8000 & \
		cd frontend && npm run dev & \
		wait

backend: ## Start only the backend (FastAPI)
	cd backend && PYTHONPATH=../src uvicorn app.main:app --reload --port 8000

frontend: ## Start only the frontend (Vite)
	cd frontend && npm run dev

# ── CLI Commands ───────────────────────────────────────────────────────

search: ## Run job search (CLI, no UI needed)
	python -m job_finder.main search $(if $(PROFILE),--profile $(PROFILE))

score: ## Search + score jobs against resume
	python -m job_finder.main score $(if $(PROFILE),--profile $(PROFILE))

run: ## Full pipeline: search + score + AI enhance
	python -m job_finder.main $(if $(PROFILE),--profile $(PROFILE))

# ── Docker ─────────────────────────────────────────────────────────────

docker: ## Start everything with Docker Compose
	docker compose up --build

docker-down: ## Stop Docker services
	docker compose down

# ── Utilities ──────────────────────────────────────────────────────────

typecheck: ## Run TypeScript type checking
	cd frontend && npx tsc --noEmit

clean: ## Remove generated files (DB, caches, node_modules)
	rm -rf data/*.db
	rm -rf src/job_finder/output/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
