# node9-python

Execution security for Python AI agents — audit, policy enforcement, and DLP in one package. One decorator, zero config.

Works two ways:
- **`@protect`** — add governance to any existing agent (LangChain, CrewAI, AutoGen, plain Python)
- **`Node9Agent`** — build a governed agent from scratch with tools, DLP, and audit built-in

## Install

```bash
pip install node9
```

## Routing

node9 automatically routes to the right backend:

| Environment | Routing |
|---|---|
| `NODE9_API_KEY` set | → node9 SaaS (cloud / CI — no local daemon needed) |
| Local daemon running | → node9-proxy on `localhost:7391` |
| Neither | → offline audit log at `~/.node9/audit.log` (auto-approve, never blocks) |

No config required — it just works wherever your agent runs.

---

## Option 1 — `@protect`: Add governance to any agent

Drop `@protect` on any function your agent calls. node9 intercepts the call, logs it, and enforces policy before the function runs.

```python
from node9 import protect, ActionDeniedException

@protect
def write_file(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)

@protect("bash")
def run_shell(command: str) -> str:
    import subprocess
    # Note: @protect gates on human approval but does NOT sanitize `command`.
    # Use shlex.split() + shell=False for untrusted input.
    return subprocess.check_output(command, shell=True, text=True)

try:
    write_file("/etc/hosts", "bad content")
except ActionDeniedException as e:
    print(f"Blocked: {e}")
```

Works with `async def` out of the box.

### Set agent identity (optional but recommended)

```python
from node9 import configure

configure(agent_name="my-langchain-agent", policy="audit")
```

Or via environment variables:
```bash
NODE9_AGENT_NAME=my-langchain-agent
NODE9_AGENT_POLICY=audit
```

### Policy values

| Policy | Behaviour |
|---|---|
| `audit` | Log everything, auto-approve. Never blocks. Good for CI. |
| `require_approval` | Block + notify human. Good for production actions. |
| `block_on_rules` | Auto-block if rules match, audit otherwise. |
| _(empty)_ | SaaS default behaviour. |

### LangChain

```python
from langchain.tools import BaseTool
from node9 import protect

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file."

    @protect("write_file")
    def _run(self, path: str, content: str) -> str:
        with open(path, "w") as f:
            f.write(content)
        return f"Written to {path}"
```

### CrewAI

```python
from crewai.tools import tool
from node9 import protect

@tool("write_file")
@protect("write_file")
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Written to {path}"
```

See [`examples/`](examples/) for full runnable examples including AutoGen and LangGraph.

---

## Option 2 — `Node9Agent`: Build a governed agent from scratch

`Node9Agent` is a governance base class — DLP, path safety, audit, and tool dispatch built-in. It does **not** include an LLM loop; that is your framework's responsibility. This keeps the SDK framework-agnostic with zero dependencies.

```python
import anthropic
from node9 import Node9Agent, tool, internal

class CiAgent(Node9Agent):
    agent_name = "ci-code-review"
    policy     = "audit"

    @tool("run_tests")
    def run_tests(self, command: str) -> str:
        """Run the test suite and return output."""
        import subprocess
        # Note: @protect gates on human approval but does NOT sanitize `command`.
    # Use shlex.split() + shell=False for untrusted input.
    return subprocess.check_output(command, shell=True, text=True)

    @tool("write_code")
    def write_code(self, filename: str, content: str) -> str:
        """Write content to a file in the workspace."""
        with open(filename, "w") as f:
            f.write(content)
        return f"Written {filename}"

    @internal
    def _git_push(self, branch: str) -> str:
        """Push to remote — infrastructure, not a governed action."""
        import subprocess
        subprocess.run(["git", "push", "origin", branch], check=True)
        return f"Pushed {branch}"

agent  = CiAgent(workspace="/path/to/repo")
client = anthropic.Anthropic()

# Get tool specs in the format your LLM expects
tools = agent.build_tools_anthropic()   # → input_schema format
# tools = agent.build_tools_openai()   # → {type: function, function: {...}}
# tools = agent._build_tools()         # → neutral (parameters key)

# Your LLM loop — use whichever client you want
messages = [{"role": "user", "content": "Fix the failing tests in this diff: ..."}]
while True:
    response = client.messages.create(model="claude-opus-4-6", tools=tools, messages=messages)
    messages.append({"role": "assistant", "content": response.content})
    if response.stop_reason != "tool_use":
        break
    results = []
    for block in response.content:
        if block.type == "tool_use":
            result = agent.dispatch(block.name, block.input)  # DLP + audit happen here
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
    messages.append({"role": "user", "content": results})
```

See [`examples/`](examples/) for complete runnable implementations per framework.

### What `@tool` does automatically

Every `@tool`-decorated method, before the function runs:
1. **DLP scan** — blocks if `filename` or `content` contains a secret or sensitive path
2. **Path safety** — rejects `../` traversal attempts, raises `ActionDeniedException`
3. **Audit / approval** — calls `evaluate()` which respects the agent's `policy`
4. **Run ID** — injects a UUID grouping all tool calls from one session in the dashboard

### What `@internal` does

`@internal` is for git operations, workspace setup, and other infrastructure:
- Never calls `evaluate()` — no SaaS call, no blocking
- Logs locally only: `[node9 internal] _git_push(branch='main')`

### Tool specs are auto-generated

`Node9Agent` introspects `@tool` methods and builds tool specs automatically — parameter names, types from annotations, and descriptions from docstrings. No manual schema writing.

---

## DLP and path safety as standalone utilities

```python
from node9 import dlp_scan, safe_path

# Scan content for secrets before writing to disk
hit = dlp_scan("output.txt", content)
if hit:
    raise ValueError(f"Blocked: {hit}")

# Resolve a path safely within a workspace directory
path = safe_path("src/main.py", workspace="/tmp/repo")
```

Patterns detected: AWS keys, GitHub tokens, Slack tokens, OpenAI keys, Stripe keys, PEM private keys, GCP service accounts, NPM auth tokens, Anthropic keys, and sensitive file paths (`.ssh`, `.aws`, `.env`, `.kube`, etc.).

---

## Handling denials in LLM feedback loops

`ActionDeniedException` has a `negotiation` property — feed it back to the LLM so it can try a different approach:

```python
try:
    agent.dispatch("delete_file", {"path": "/etc/hosts"})
except ActionDeniedException as e:
    # e.negotiation = "Action 'delete_file' was blocked by Node9: policy. Choose a different approach."
    response = llm.invoke(e.negotiation)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NODE9_API_KEY` | — | Routes to node9 SaaS. Required for cloud / CI. |
| `NODE9_AGENT_NAME` | — | Agent identity — appears in audit logs and dashboard. |
| `NODE9_AGENT_POLICY` | — | `audit`, `require_approval`, or `block_on_rules`. |
| `NODE9_DAEMON_PORT` | `7391` | Local daemon port. |
| `NODE9_AUTO_START` | — | Set to `1` to auto-launch the local daemon if not running. |
| `NODE9_SKIP` | — | Set to `1` to bypass all checks. Unsafe — for unit tests only. |

## License

Apache-2.0
