#!/usr/bin/env bash
# Shared test runner sourced by pre-commit and pre-push hooks.
# Usage: source run-tests.sh <context>  (context = "commit" | "push")
#
# NOTE: uses `return` not `exit` — this script is sourced, not executed.
# `exit` in a sourced script terminates the parent shell; `return` only
# exits the script's scope, leaving the caller's shell intact.
set -euo pipefail

CONTEXT="${1:-commit}"

# Use the virtualenv Python if active, otherwise fall back to python3.
PYTHON="${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}"
PYTHON="${PYTHON:-$(command -v python3 2>/dev/null)}"

if [[ -z "$PYTHON" ]]; then
  echo "❌ node9: python3 not found on PATH. Install Python 3.9+ and try again." >&2
  return 1
fi

# Sanity-check: require Python 3.9+
PYVER=$("$PYTHON" -c 'import sys; print(sys.version_info >= (3,9))' 2>/dev/null)
if [[ "$PYVER" != "True" ]]; then
  echo "❌ node9: Python 3.9+ required (found: $("$PYTHON" --version 2>&1))" >&2
  return 1
fi

echo "🧪 node9: running tests before ${CONTEXT}..."

if ! "$PYTHON" -m pytest tests/ -p no:anyio -q --tb=short; then
  echo ""
  echo "❌ Tests failed — ${CONTEXT} blocked. Fix the failures above and try again."
  echo "   To skip (unsafe): git ${CONTEXT} --no-verify"
  return 1
fi

echo "✅ All tests passed."
