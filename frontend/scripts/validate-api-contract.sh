#!/usr/bin/env bash
# Validates that frontend TypeScript types match the backend OpenAPI spec.
#
# Usage:
#   ./scripts/validate-api-contract.sh
#
# Prerequisites:
#   - Backend running at localhost:8000
#   - npm dependencies installed (openapi-typescript)
#
# This script:
#   1. Generates fresh types from the live backend OpenAPI spec
#   2. Compares with the checked-in generated types
#   3. Runs tsc to verify handwritten types compile against the API
#   4. Exits non-zero if anything is out of sync

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GENERATED_FILE="$FRONTEND_DIR/src/types/api.generated.ts"
TEMP_FILE=$(mktemp)

cd "$FRONTEND_DIR"

echo "--- Checking backend is reachable ---"
if ! curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  echo "ERROR: Backend not running at localhost:8000"
  echo "Start it with: cd backend && uvicorn app.main:app --port 8000"
  exit 1
fi

echo "--- Generating types from OpenAPI spec ---"
npx openapi-typescript http://localhost:8000/openapi.json -o "$TEMP_FILE" 2>/dev/null

echo "--- Comparing with checked-in types ---"
if [ -f "$GENERATED_FILE" ]; then
  if diff -q "$GENERATED_FILE" "$TEMP_FILE" > /dev/null 2>&1; then
    echo "OK: Generated types are up to date"
  else
    echo "DRIFT DETECTED: api.generated.ts is out of date"
    echo "Run: npm run generate-types"
    diff "$GENERATED_FILE" "$TEMP_FILE" | head -30
    rm "$TEMP_FILE"
    exit 1
  fi
else
  echo "WARNING: api.generated.ts not found, creating it"
  cp "$TEMP_FILE" "$GENERATED_FILE"
fi

rm -f "$TEMP_FILE"

echo "--- Running TypeScript check ---"
npx tsc --noEmit
echo "OK: All types compile"

echo ""
echo "Contract validation passed."
