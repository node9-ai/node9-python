#!/usr/bin/env bash
# Shared test runner sourced by pre-commit and pre-push hooks.
# Usage: source run-tests.sh <context>  (context = "commit" | "push")
#
# NOTE: uses `return` not `exit` — this script is sourced, not executed.
# `exit` in a sourced script terminates the parent shell; `return` only
# exits the script's scope, leaving the caller's shell intact.
set -euo pipefail

CONTEXT="${1:-commit}"

# Use the virtualenv Python if active, otherwise fall back to system python3.
# Check python3 first inside the venv (most venvs only create python3, not python).
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
  if [[ -x "$VIRTUAL_ENV/bin/python3" ]]; then
    PYTHON="$VIRTUAL_ENV/bin/python3"
  elif [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON="$VIRTUAL_ENV/bin/python"
  else
    PYTHON="$(command -v python3 2>/dev/null)"
  fi
else
  PYTHON="$(command -v python3 2>/dev/null)"
fi

if [[ -z "$PYTHON" ]]; then
  echo "❌ node9: python3 not found on PATH. Install Python 3.10+ and try again." >&2
  return 1
fi

# Sanity-check: require Python 3.10+ (matches pyproject.toml requires-python)
PYVER=$("$PYTHON" -c 'import sys; print(sys.version_info >= (3,10))' 2>/dev/null)
if [[ "$PYVER" != "True" ]]; then
  echo "❌ node9: Python 3.10+ required (found: $("$PYTHON" --version 2>&1))" >&2
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
