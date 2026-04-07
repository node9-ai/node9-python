#!/usr/bin/env bash
# Shared test runner sourced by pre-commit and pre-push hooks.
# Usage: source run-tests.sh <context>  (context = "commit" | "push")
set -euo pipefail

CONTEXT="${1:-commit}"

# Use the virtualenv Python if active, otherwise fall back to python3.
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
PYTHON="${PYTHON:-$(command -v python3)}"

echo "🧪 node9: running tests before ${CONTEXT}..."

if ! "$PYTHON" -m pytest tests/ -p no:anyio -q --tb=short; then
  echo ""
  echo "❌ Tests failed — ${CONTEXT} blocked. Fix the failures above and try again."
  echo "   To skip (unsafe): git ${CONTEXT} --no-verify"
  exit 1
fi

echo "✅ All tests passed."
