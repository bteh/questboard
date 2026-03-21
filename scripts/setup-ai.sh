#!/usr/bin/env bash
# Setup AI for Launchboard — installs Ollama + pulls a model so AI works out of the box.
# Called by `make setup`. Can also be run standalone: ./scripts/setup-ai.sh

set -euo pipefail

MODEL="llama3.2:3b"   # 2GB, fast on CPU, good enough for job scoring
MODEL_SIZE="2 GB"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
DIM='\033[2m'
NC='\033[0m'

info()  { printf "  ${BLUE}%s${NC}\n" "$1"; }
ok()    { printf "  ${GREEN}✓${NC} %s\n" "$1"; }
warn()  { printf "  ${YELLOW}%s${NC}\n" "$1"; }

# ── Check if Ollama is already installed ──────────────────────────────

if command -v ollama &>/dev/null; then
    ok "Ollama is installed ($(ollama --version 2>/dev/null || echo 'unknown version'))"
    OLLAMA_INSTALLED=1
else
    OLLAMA_INSTALLED=0
fi

# ── Check if a model is already available ────────────────────────────

has_model() {
    ollama list 2>/dev/null | grep -q . 2>/dev/null
}

if [ "$OLLAMA_INSTALLED" = "1" ] && has_model; then
    ok "Ollama already has models — AI is ready"
    # Write config if not already set
    if [ -f .env ] && ! grep -q "^LLM_PROVIDER=" .env 2>/dev/null; then
        DETECTED_MODEL=$(ollama list 2>/dev/null | awk 'NR==2{print $1}' | sed 's/:latest//')
        echo "" >> .env
        echo "# Auto-configured by setup — Ollama detected" >> .env
        echo "LLM_PROVIDER=ollama" >> .env
        echo "LLM_BASE_URL=http://localhost:11434/v1" >> .env
        echo "LLM_MODEL=${DETECTED_MODEL:-$MODEL}" >> .env
        echo "LLM_API_KEY=ollama" >> .env
        ok "Configured .env to use Ollama (${DETECTED_MODEL:-$MODEL})"
    fi
    exit 0
fi

# ── Offer to install ─────────────────────────────────────────────────

echo ""
info "AI Setup"
echo ""
echo "  Launchboard uses AI to score jobs, write cover letters, and"
echo "  research companies. The easiest option is Ollama — a free,"
echo "  private AI that runs on your machine (no account needed)."
echo ""
printf "  Install Ollama and download a model (~${MODEL_SIZE})? [Y/n] "
read -r REPLY
REPLY=${REPLY:-Y}

if [[ ! "$REPLY" =~ ^[Yy] ]]; then
    echo ""
    warn "Skipped AI setup. You can set this up later in Settings."
    echo ""
    echo "  Alternatives:"
    echo "    • Install Ollama manually: https://ollama.com"
    echo "    • Use a free cloud API: set LLM_PROVIDER=gemini in .env"
    echo "      Get a key at https://aistudio.google.com/apikey (30 seconds)"
    echo ""
    exit 0
fi

# ── Install Ollama ───────────────────────────────────────────────────

if [ "$OLLAMA_INSTALLED" = "0" ]; then
    echo ""
    info "Installing Ollama..."

    OS=$(uname -s)
    case "$OS" in
        Darwin)
            if command -v brew &>/dev/null; then
                brew install ollama 2>/dev/null || {
                    info "Downloading Ollama..."
                    curl -fsSL https://ollama.com/install.sh | sh
                }
            else
                info "Downloading Ollama..."
                curl -fsSL https://ollama.com/install.sh | sh
            fi
            ;;
        Linux)
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        *)
            warn "Automatic install not supported on $OS."
            echo "  Download manually: https://ollama.com"
            exit 0
            ;;
    esac

    if command -v ollama &>/dev/null; then
        ok "Ollama installed"
    else
        warn "Installation may have failed. Try: https://ollama.com"
        exit 1
    fi
fi

# ── Start Ollama if not running ──────────────────────────────────────

if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    info "Starting Ollama..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    # Wait for it to be ready (up to 10 seconds)
    for i in $(seq 1 20); do
        if curl -s http://localhost:11434/api/tags &>/dev/null; then
            break
        fi
        sleep 0.5
    done
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        ok "Ollama is running"
    else
        warn "Ollama started but not responding yet. It may need a moment."
    fi
fi

# ── Pull a model ─────────────────────────────────────────────────────

echo ""
info "Downloading AI model ($MODEL, ~$MODEL_SIZE)..."
echo "  ${DIM}This is a one-time download.${NC}"
echo ""

if ollama pull "$MODEL"; then
    ok "Model downloaded: $MODEL"
else
    warn "Model download failed. You can retry later: ollama pull $MODEL"
    exit 1
fi

# ── Configure .env ───────────────────────────────────────────────────

if [ -f .env ]; then
    # Remove any existing LLM config lines
    sed -i.bak '/^LLM_PROVIDER=/d; /^LLM_BASE_URL=/d; /^LLM_MODEL=/d; /^LLM_API_KEY=/d; /^# Auto-configured by setup/d' .env 2>/dev/null || true
    rm -f .env.bak
fi

echo "" >> .env
echo "# Auto-configured by setup — Ollama" >> .env
echo "LLM_PROVIDER=ollama" >> .env
echo "LLM_BASE_URL=http://localhost:11434/v1" >> .env
echo "LLM_MODEL=$MODEL" >> .env
echo "LLM_API_KEY=ollama" >> .env

ok "Configured .env to use Ollama ($MODEL)"

echo ""
ok "AI is ready! When you run 'make dev', AI scoring will work automatically."
echo ""
