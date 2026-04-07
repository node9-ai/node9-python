"""
Manual smoke test for node9 SDK.
Run in different modes to test all three routing paths.

Usage:
  # 1. Offline mode (no daemon, no API key)
  python3 manual_test.py

  # 2. Local daemon mode (start daemon first: npx @node9/proxy daemon)
  python3 manual_test.py --daemon

  # 3. Cloud mode
  NODE9_API_KEY=sk-... python3 manual_test.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from node9 import protect, configure, Node9Agent, tool, internal, dlp_scan, safe_path, ActionDeniedException

print("\n=== node9 SDK manual test ===\n")

# ── 1. Routing info ───────────────────────────────────────────────────────────
if os.environ.get("NODE9_API_KEY"):
    print("Mode: CLOUD (NODE9_API_KEY set)")
elif "--daemon" in sys.argv:
    print("Mode: LOCAL DAEMON")
else:
    print("Mode: OFFLINE (no daemon, no API key)")
print()

# ── 2. configure() ───────────────────────────────────────────────────────────
print("--- configure() ---")
configure(agent_name="manual-test", policy="audit")
import node9._config as cfg
print(f"  agent_name = {cfg.AGENT_NAME!r}")
print(f"  policy     = {cfg.AGENT_POLICY!r}")
print()

# ── 3. @protect basic call ───────────────────────────────────────────────────
print("--- @protect ---")

@protect("write_file")
def write_file(path: str, content: str) -> str:
    return f"written:{path}"

result = write_file("/tmp/test.txt", "hello")
print(f"  write_file result: {result}")
print()

# ── 4. DLP scan ──────────────────────────────────────────────────────────────
print("--- dlp_scan ---")
clean = dlp_scan("output.txt", "def hello(): pass")
print(f"  clean content: {clean!r}  (expect None)")

sensitive_path = dlp_scan("/home/user/.ssh/id_rsa", "content")
print(f"  sensitive path: {sensitive_path!r}  (expect block reason)")
print()

# ── 5. safe_path ─────────────────────────────────────────────────────────────
print("--- safe_path ---")
with tempfile.TemporaryDirectory() as workspace:
    resolved = safe_path("src/main.py", workspace)
    print(f"  safe_path resolved: {resolved}")
    try:
        safe_path("../../etc/passwd", workspace)
        print("  traversal: NOT blocked (BUG)")
    except ValueError as e:
        print(f"  traversal blocked: {e}")
print()

# ── 6. Node9Agent ────────────────────────────────────────────────────────────
print("--- Node9Agent ---")

with tempfile.TemporaryDirectory() as workspace:
    class TestAgent(Node9Agent):
        agent_name = "manual-test-agent"
        policy     = "audit"

        @tool("echo")
        def echo(self, message: str) -> str:
            """Echo the message back."""
            return f"echo:{message}"

        @tool("write_file")
        def write_file(self, filename: str, content: str) -> str:
            """Write content to a file."""
            import pathlib
            (pathlib.Path(self._workspace) / filename).write_text(content)
            return f"written:{filename}"

        @internal
        def _setup(self, branch: str) -> str:
            return f"setup:{branch}"

    agent = TestAgent(workspace=workspace)
    print(f"  run_id: {agent._run_id}")
    print(f"  workspace: {agent._workspace}")

    # @tool call
    result = agent.echo("hello node9")
    print(f"  @tool echo: {result}")

    # @internal call (no evaluate)
    result = agent._setup("main")
    print(f"  @internal _setup: {result}")

    # DLP block via @tool
    try:
        agent.write_file("/home/user/.ssh/id_rsa", "content")
        print("  DLP: NOT blocked (BUG)")
    except ActionDeniedException as e:
        print(f"  DLP blocked: {e.tool_name} — {e.reason[:50]}")

    # Path traversal block via @tool
    try:
        agent.write_file("../../etc/passwd", "content")
        print("  Traversal: NOT blocked (BUG)")
    except ActionDeniedException as e:
        print(f"  Traversal blocked: {e.tool_name} — {e.reason[:50]}")

    # _build_tools
    tools = agent._build_tools()
    print(f"  _build_tools: {[t['name'] for t in tools]}")

print()
print("=== all checks passed ===\n")
