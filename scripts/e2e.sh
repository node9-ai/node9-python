#!/usr/bin/env bash
# =============================================================================
# Node9 Python SDK — End-to-End Test
# Tests the decorator, client, and exception flow without a live daemon.
# Run from the repo root: bash scripts/e2e.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}✓${RESET} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗${RESET} $1"; FAIL=$((FAIL+1)); }
section() { echo -e "\n${BOLD}${BLUE}── $1 ──${RESET}"; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# =============================================================================
# PART 1 — NODE9_SKIP bypass
# =============================================================================
section "Part 1 · NODE9_SKIP=1 bypasses all checks"

out=$(NODE9_SKIP=1 python3 -c "
from node9 import protect
@protect
def dangerous(cmd): return 'ran'
print(dangerous('rm -rf /'))
" 2>&1)

if echo "$out" | grep -q "ran"; then
  pass "NODE9_SKIP=1 allows decorated function to run"
else
  fail "NODE9_SKIP=1 did not bypass check (got: '$out')"
fi

# =============================================================================
# PART 2 — DaemonNotFoundError when no daemon running
# =============================================================================
section "Part 2 · DaemonNotFoundError when daemon is not running"

out=$(NODE9_DAEMON_PORT=19999 python3 -c "
from node9 import protect, DaemonNotFoundError
@protect
def write_file(path): pass
try:
    write_file('/tmp/test')
    print('no_error')
except DaemonNotFoundError:
    print('daemon_not_found')
except Exception as e:
    print(f'wrong_error: {e}')
" 2>&1)

if echo "$out" | grep -q "daemon_not_found"; then
  pass "DaemonNotFoundError raised when daemon unreachable"
else
  fail "Expected DaemonNotFoundError (got: '$out')"
fi

# =============================================================================
# PART 3 — ActionDeniedException fields
# =============================================================================
section "Part 3 · ActionDeniedException has correct fields"

out=$(python3 -c "
from node9 import ActionDeniedException
e = ActionDeniedException('bash', 'Too dangerous')
assert e.tool_name == 'bash', f'tool_name wrong: {e.tool_name}'
assert e.reason == 'Too dangerous', f'reason wrong: {e.reason}'
assert 'bash' in e.negotiation, f'negotiation missing tool name'
assert 'Too dangerous' in e.negotiation, f'negotiation missing reason'
print('ok')
" 2>&1)

if echo "$out" | grep -q "ok"; then
  pass "ActionDeniedException has tool_name, reason, and negotiation"
else
  fail "ActionDeniedException fields wrong (got: '$out')"
fi

# =============================================================================
# PART 4 — Decorator preserves function metadata
# =============================================================================
section "Part 4 · @protect preserves function name and docstring"

out=$(NODE9_SKIP=1 python3 -c "
from node9 import protect

@protect
def my_tool(x):
    '''Does something important.'''
    return x

print(my_tool.__name__)
print(my_tool.__doc__)
" 2>&1)

if echo "$out" | grep -q "my_tool" && echo "$out" | grep -q "Does something important"; then
  pass "@protect preserves __name__ and __doc__"
else
  fail "@protect broke function metadata (got: '$out')"
fi

# =============================================================================
# PART 5 — Custom tool name and params lambda
# =============================================================================
section "Part 5 · Custom tool name and params lambda"

out=$(NODE9_SKIP=1 python3 -c "
from node9 import protect

@protect('postgres_query', params=lambda sql, db='prod', **_: {'sql': sql, 'database': db})
def execute_sql(sql, db='prod'):
    return f'ran:{sql}:{db}'

print(execute_sql('SELECT 1', db='staging'))
" 2>&1)

if echo "$out" | grep -q "ran:SELECT 1:staging"; then
  pass "Custom tool name + params lambda works"
else
  fail "Custom params lambda failed (got: '$out')"
fi

# =============================================================================
# PART 6 — Async decorator (Python 3.10+)
# =============================================================================
section "Part 6 · Async @protect"

out=$(NODE9_SKIP=1 python3 -c "
import asyncio
from node9 import protect

@protect
async def async_tool(x):
    return f'async:{x}'

result = asyncio.run(async_tool('hello'))
print(result)
" 2>&1)

if echo "$out" | grep -q "async:hello"; then
  pass "Async @protect works with NODE9_SKIP=1"
else
  fail "Async @protect failed (got: '$out')"
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo -e "\n${BOLD}══════════════════════════════════════════${RESET}"
TOTAL=$((PASS + FAIL))
if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}  All $TOTAL tests passed ✓${RESET}"
else
  echo -e "${RED}${BOLD}  $FAIL/$TOTAL tests FAILED${RESET}"
fi
echo -e "${BOLD}══════════════════════════════════════════${RESET}\n"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
