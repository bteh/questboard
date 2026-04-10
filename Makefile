.PHONY: help setup dev dev-hosted stop-dev backend frontend search clean docker doctor doctor-env dev-hosted-reset desktop-dev desktop-build desktop-install desktop-smoke

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
	@normalize_pids() { printf '%s\n' "$$*" | tr ' ' '\n' | sed '/^$$/d' | sort -u | xargs 2>/dev/null || true; }; \
	describe_pids() { for pid in $$*; do cmd=$$(ps -o command= -p "$$pid" 2>/dev/null | head -n 1); [ -n "$$cmd" ] || cmd="(process exited)"; echo "    $$pid $$cmd"; done; }; \
	backend_pid=$$(normalize_pids "$$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"); \
	frontend_pid=$$(normalize_pids "$$(lsof -tiTCP:5173 -sTCP:LISTEN 2>/dev/null || true)"); \
	if [ -n "$$backend_pid" ] || [ -n "$$frontend_pid" ]; then \
		echo "  Existing dev server detected."; \
		if [ -n "$$backend_pid" ]; then \
			echo "  Port 8000 in use by:"; \
			describe_pids $$backend_pid; \
		fi; \
		if [ -n "$$frontend_pid" ]; then \
			echo "  Port 5173 in use by:"; \
			describe_pids $$frontend_pid; \
		fi; \
		echo ""; \
		echo "  Run 'make stop-dev' first, or kill those processes manually."; \
		echo ""; \
		exit 1; \
	fi
	@trap 'kill 0' EXIT; \
		cd backend && PYTHONPATH=../src $(CURDIR)/$(PYTHON) -m uvicorn app.main:app --reload --reload-dir . --reload-dir ../src --host 127.0.0.1 --port 8000 & \
		cd frontend && npm run dev & \
		wait

dev-hosted: .venv ## Start the hosted-like local sandbox with persona auth + worker
	@echo "\n  Starting Launchboard hosted sandbox...\n"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:5173"
	@echo "  Mode:     hosted sandbox with test-account auth"
	@echo "  Press Ctrl+C to stop\n"
	@normalize_pids() { printf '%s\n' "$$*" | tr ' ' '\n' | sed '/^$$/d' | sort -u | xargs 2>/dev/null || true; }; \
	describe_pids() { for pid in $$*; do cmd=$$(ps -o command= -p "$$pid" 2>/dev/null | head -n 1); [ -n "$$cmd" ] || cmd="(process exited)"; echo "    $$pid $$cmd"; done; }; \
	backend_pid=$$(normalize_pids "$$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"); \
	frontend_pid=$$(normalize_pids "$$(lsof -tiTCP:5173 -sTCP:LISTEN 2>/dev/null || true)"); \
	worker_pid=$$(normalize_pids "$$(pgrep -f 'scripts/dev_hosted_worker.py' 2>/dev/null || true) $$(pgrep -f 'HOSTED_MODE=true DEV_HOSTED_AUTH=true' 2>/dev/null || true) $$(pgrep -f 'launchboard-dev-hosted-workspace-secret' 2>/dev/null || true)"); \
	if [ -n "$$backend_pid" ] || [ -n "$$frontend_pid" ] || [ -n "$$worker_pid" ]; then \
		echo "  Existing Launchboard process detected."; \
		if [ -n "$$backend_pid" ]; then \
			echo "  Port 8000 in use by:"; \
			describe_pids $$backend_pid; \
		fi; \
		if [ -n "$$frontend_pid" ]; then \
			echo "  Port 5173 in use by:"; \
			describe_pids $$frontend_pid; \
		fi; \
		if [ -n "$$worker_pid" ]; then \
			echo "  Worker or hosted sandbox shell running:"; \
			describe_pids $$worker_pid; \
		fi; \
		echo ""; \
		echo "  Run 'make stop-dev' first, or kill those processes manually."; \
		echo ""; \
		exit 1; \
	fi
	@mkdir -p data/dev-hosted/workspaces
	@trap 'kill 0' EXIT; \
		cd backend && HOSTED_MODE=true DEV_HOSTED_AUTH=true HOSTED_ALLOW_WORKSPACE_LLM_CONFIG=true LAUNCHBOARD_SECRET=launchboard-dev-hosted-workspace-secret MANAGE_SCHEMA_ON_STARTUP=true EMBEDDED_SCHEDULER_ENABLED=false DATA_DIR=$(CURDIR)/data/dev-hosted WORKSPACE_STORAGE_DIR=$(CURDIR)/data/dev-hosted/workspaces PYTHONPATH=../src $(CURDIR)/$(PYTHON) -m uvicorn app.main:app --reload --reload-dir . --reload-dir ../src --host 127.0.0.1 --port 8000 & \
		HOSTED_MODE=true DEV_HOSTED_AUTH=true HOSTED_ALLOW_WORKSPACE_LLM_CONFIG=true LAUNCHBOARD_SECRET=launchboard-dev-hosted-workspace-secret MANAGE_SCHEMA_ON_STARTUP=true EMBEDDED_SCHEDULER_ENABLED=false DATA_DIR=$(CURDIR)/data/dev-hosted WORKSPACE_STORAGE_DIR=$(CURDIR)/data/dev-hosted/workspaces PYTHONPATH=$(CURDIR)/src $(CURDIR)/$(PYTHON) scripts/dev_hosted_worker.py & \
		cd frontend && VITE_API_URL=http://localhost:8000/api/v1 VITE_HOSTED_MODE=true VITE_DEV_HOSTED_AUTH=true npm run dev -- --port 5173 & \
		backend_ready=0; \
		for attempt in $$(seq 1 30); do \
			if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then \
				backend_ready=1; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ "$$backend_ready" -ne 1 ]; then \
			echo "  Hosted sandbox failed to start the backend."; \
			exit 1; \
		fi; \
		worker_ready=0; \
		for attempt in $$(seq 1 30); do \
			if curl -fsS http://localhost:8000/health/worker 2>/dev/null | grep -q '"status":"ok"'; then \
				worker_ready=1; \
				break; \
			fi; \
			sleep 1; \
		done; \
		if [ "$$worker_ready" -ne 1 ]; then \
			echo "  Hosted sandbox backend started, but the worker did not become healthy."; \
			echo "  Search will still fall back inline locally, but fix the worker before relying on queue behavior."; \
		else \
			echo "  Hosted sandbox is healthy."; \
			echo ""; \
		fi; \
		wait

stop-dev: ## Stop Launchboard dev servers started from this repo
	@normalize_pids() { printf '%s\n' "$$*" | tr ' ' '\n' | sed '/^$$/d' | sort -u | xargs 2>/dev/null || true; }; \
	pid_cwd() { lsof -a -p "$$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1; }; \
	is_launchboard_pid() { \
		pid="$$1"; \
		cwd=$$(pid_cwd "$$pid"); \
		cmd=$$(ps -o command= -p "$$pid" 2>/dev/null | head -n 1); \
		case "$$cwd" in \
			"$(CURDIR)"*) return 0 ;; \
		esac; \
		case "$$cmd" in \
			*"$(CURDIR)"*) return 0 ;; \
		esac; \
		return 1; \
	}; \
	filter_launchboard_pids() { \
		for pid in $$*; do \
			[ -n "$$pid" ] || continue; \
			if is_launchboard_pid "$$pid"; then \
				echo "$$pid"; \
			fi; \
		done | sort -u | xargs 2>/dev/null || true; \
	}; \
	candidates=$$(normalize_pids "$$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true) $$(lsof -tiTCP:5173 -sTCP:LISTEN 2>/dev/null || true) $$(lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null || true) $$(pgrep -f 'scripts/dev_hosted_worker.py' 2>/dev/null || true) $$(pgrep -f 'HOSTED_MODE=true DEV_HOSTED_AUTH=true' 2>/dev/null || true) $$(pgrep -f 'launchboard-dev-hosted-workspace-secret' 2>/dev/null || true) $$(pgrep -f 'launchboard-desktop' 2>/dev/null || true)"); \
	pids=$$(filter_launchboard_pids $$candidates); \
	if [ -z "$$pids" ]; then \
		echo "  No Launchboard dev servers found."; \
		exit 0; \
	fi; \
	echo "  Stopping Launchboard dev servers: $$pids"; \
	kill $$pids 2>/dev/null || true; \
	sleep 1; \
	remaining_candidates=$$(normalize_pids "$$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true) $$(lsof -tiTCP:5173 -sTCP:LISTEN 2>/dev/null || true) $$(lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null || true) $$(pgrep -f 'scripts/dev_hosted_worker.py' 2>/dev/null || true) $$(pgrep -f 'HOSTED_MODE=true DEV_HOSTED_AUTH=true' 2>/dev/null || true) $$(pgrep -f 'launchboard-dev-hosted-workspace-secret' 2>/dev/null || true) $$(pgrep -f 'launchboard-desktop' 2>/dev/null || true)"); \
	remaining=$$(filter_launchboard_pids $$remaining_candidates); \
	if [ -n "$$remaining" ]; then \
		echo "  Force stopping stubborn processes: $$remaining"; \
		kill -9 $$remaining 2>/dev/null || true; \
	fi

backend: .venv ## Start only the backend (FastAPI)
	cd backend && PYTHONPATH=../src $(CURDIR)/$(PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend: ## Start only the frontend (Vite)
	cd frontend && npm run dev

desktop-dev: .venv ## Start Launchboard in Tauri desktop dev mode
	@CARGO_BIN=$$(command -v cargo 2>/dev/null || printf '%s/.cargo/bin/cargo' "$$HOME"); \
	if [ ! -x "$$CARGO_BIN" ]; then \
		echo "  Rust toolchain not found. Install rustup from https://rustup.rs first."; \
		exit 1; \
	fi; \
	normalize_pids() { printf '%s\n' "$$*" | tr ' ' '\n' | sed '/^$$/d' | sort -u | xargs 2>/dev/null || true; }; \
	describe_pids() { for pid in $$*; do cmd=$$(ps -o command= -p "$$pid" 2>/dev/null | head -n 1); [ -n "$$cmd" ] || cmd="(process exited)"; echo "    $$pid $$cmd"; done; }; \
	dev_port_pid=$$(normalize_pids "$$(lsof -tiTCP:5173 -sTCP:LISTEN 2>/dev/null || true)"); \
	runtime_port_pid=$$(normalize_pids "$$(lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null || true)"); \
	if [ -n "$$dev_port_pid" ] || [ -n "$$runtime_port_pid" ]; then \
		echo "  Existing desktop dev process detected."; \
		if [ -n "$$dev_port_pid" ]; then \
			echo "  Port 5173 in use by:"; \
			describe_pids $$dev_port_pid; \
		fi; \
		if [ -n "$$runtime_port_pid" ]; then \
			echo "  Port 8765 in use by:"; \
			describe_pids $$runtime_port_pid; \
		fi; \
		echo ""; \
		echo "  Run 'make stop-dev' first, or kill those processes manually."; \
		echo ""; \
		exit 1; \
	fi; \
	export PATH="$$(dirname "$$CARGO_BIN"):$${PATH}"; \
	cd frontend && npm run desktop:dev

desktop-build: .venv ## Build the Tauri desktop app
	@CARGO_BIN=$$(command -v cargo 2>/dev/null || printf '%s/.cargo/bin/cargo' "$$HOME"); \
	if [ ! -x "$$CARGO_BIN" ]; then \
		echo "  Rust toolchain not found. Install rustup from https://rustup.rs first."; \
		exit 1; \
	fi; \
	export PATH="$$(dirname "$$CARGO_BIN"):$${PATH}"; \
	cd frontend && npm run desktop:build

desktop-install: .venv desktop-build ## Install the latest built Launchboard.app into /Applications
	$(PYTHON) scripts/install_desktop_app.py

desktop-smoke: .venv ## Run the desktop UX smoke test against the local runtime + web UI
	cd frontend && npm run desktop:smoke

dev-hosted-reset: ## Remove local hosted sandbox data after stopping dev processes
	@$(MAKE) stop-dev >/dev/null 2>&1 || true
	rm -rf data/dev-hosted
	@echo "  Removed hosted sandbox data from data/dev-hosted"

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

doctor: doctor-env ## Run full health check (env + runtime app state)
	@echo ""
	@.venv/bin/python scripts/doctor.py 2>/dev/null || python3 scripts/doctor.py

doctor-env: ## Check your dev environment for common install/setup issues
	@echo "\n  Launchboard — Doctor (env)\n"
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
	printf "  Rust (desktop): "; \
	if cargo --version 2>/dev/null; then \
		true; \
	else \
		echo "OPTIONAL — install rustup from https://rustup.rs for desktop app development"; \
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
	printf "  PyInstaller:    "; \
	if .venv/bin/python -m PyInstaller --version >/dev/null 2>&1; then \
		echo "ok"; \
	else \
		echo "OPTIONAL — run 'make setup' to install desktop packaging support"; \
	fi; \
	printf "  Playwright:     "; \
	if test -x frontend/node_modules/.bin/playwright; then \
		echo "installed"; \
	else \
		echo "OPTIONAL — run 'cd frontend && npm install' for desktop smoke tests"; \
	fi; \
	printf "  Desktop target: "; \
	if .venv/bin/python -c "import platform, sys; machine=platform.machine().lower(); system=sys.platform; mapping={('darwin','x86_64'):'x86_64-apple-darwin',('darwin','arm64'):'aarch64-apple-darwin',('darwin','aarch64'):'aarch64-apple-darwin'}; print(mapping.get((system,machine), machine))" 2>/dev/null; then \
		if [ "$$(uname -m 2>/dev/null || echo unknown)" != "$$(.venv/bin/python -c "import platform; print(platform.machine().lower())" 2>/dev/null || echo unknown)" ]; then \
			echo "                   note: release builds follow Python architecture; install a native Python for native desktop bundles."; \
		fi; \
	else \
		echo "unknown"; \
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
	rm -rf data/dev-hosted
	rm -rf .desktop-build
	rm -f frontend/src-tauri/resources/sidecars/launchboard-runtime frontend/src-tauri/resources/sidecars/launchboard-runtime.exe
	rm -f .desktop-build/tauri-sidecars/launchboard-runtime .desktop-build/tauri-sidecars/launchboard-runtime.exe
	rm -rf src/job_finder/output/*
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

reset: ## Full reset (removes venv + node_modules, then re-runs setup)
	rm -rf .venv frontend/node_modules
	$(MAKE) setup
