#!/usr/bin/env bash
# Re-authenticate the cliproxyapi daemon with Claude.
#
# Why this exists: cliproxyapi runs as a brew-managed background service
# but doesn't auto-refresh Claude OAuth tokens reliably. When the token
# expires (~12-24h cadence), every request to the proxy fails with
# `auth_unavailable` and Questboard shows "AI disconnected". The fix is
# to stop the daemon, run `cliproxyapi -login` interactively to capture
# a fresh OAuth code, then restart the daemon.
#
# Usage:  ./scripts/reauth-claude-proxy.sh

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info() { printf "${GREEN}==>${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!! ${NC} %s\n" "$*"; }
die()  { printf "${RED}!! ${NC} %s\n" "$*" >&2; exit 1; }

command -v cliproxyapi >/dev/null 2>&1 || die "cliproxyapi not installed. Run: brew install cliproxyapi"
command -v brew >/dev/null 2>&1 || die "Homebrew not found — this script targets the brew-managed cliproxyapi"

info "Stopping cliproxyapi daemon (frees port 8317)..."
brew services stop cliproxyapi >/dev/null

# Give the daemon a moment to release the port before -login binds it.
sleep 1

info "Launching interactive OAuth login — your browser will open."
echo
warn "After signing in, the proxy will write a fresh token and exit."
warn "Press Ctrl-C if the process hangs more than ~30 seconds after success."
echo

cliproxyapi -login || warn "cliproxyapi -login exited non-zero — that's usually fine if the auth file was written"

info "Restarting cliproxyapi daemon..."
brew services start cliproxyapi >/dev/null

# Give the proxy a moment to bind port 8317.
for i in 1 2 3 4 5; do
  if curl -sf http://localhost:8317/v1/models -o /dev/null; then
    break
  fi
  sleep 1
done

info "Verifying /v1/models..."
if curl -sf http://localhost:8317/v1/models -o /tmp/cliproxy-verify.json; then
  count=$(grep -oE '"id":"[^"]+"' /tmp/cliproxy-verify.json | wc -l | tr -d ' ')
  printf "${GREEN}OK${NC} — proxy exposes %s models\n" "$count"
else
  die "Proxy is still not responding on :8317. Check 'brew services info cliproxyapi'"
fi

echo
info "Done. Questboard's 'AI disconnected' banner will clear within 2 minutes,"
info "or hit Settings → AI → Test Connection to force-refresh."
