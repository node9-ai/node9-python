# node9-python

Execution security for Python AI agents — one decorator, zero config.

Works with any framework: plain Python, LangChain, CrewAI, LangGraph, or custom agents.

## Install

```bash
pip install node9
```

## Quick Start

**1. Start the Node9 daemon** (ships with `@node9/proxy`):

```bash
npx @node9/proxy daemon
```

**2. Add `@protect` to any function your agent calls:**

```python
from node9 import protect, ActionDeniedException

@protect
def write_file(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)

@protect("bash")
def run_shell(command: str) -> str:
    import subprocess
    return subprocess.check_output(command, shell=True, text=True)

# When your agent calls this, Node9 intercepts it and asks for approval.
# The call blocks until a human approves or denies — in the dashboard or Slack.
try:
    write_file("/etc/hosts", "malicious content")
except ActionDeniedException as e:
    print(f"Blocked: {e}")
```

That's it. All function arguments are captured automatically — no config needed.

## How It Works

```
Agent calls write_file()
       ↓
  @protect intercepts
       ↓
  POST /check → Node9 daemon (localhost:7391)
       ↓
  Daemon shows approval popup / sends Slack message
       ↓
  Human approves or denies
       ↓
  Function runs (or ActionDeniedException is raised)
```

## Async Support

`@protect` works with `async def` out of the box. The blocking HTTP call runs in a thread so it never freezes your event loop:

```python
@protect("write_file")
async def write_file(path: str, content: str) -> str:
    async with aiofiles.open(path, "w") as f:
        await f.write(content)
    return f"Written to {path}"
```

This makes it compatible with LangGraph, FastMCP, and any other async agent framework.

## Custom Tool Name

By default, the tool name sent to Node9 is the function name. Override it:

```python
@protect("postgres_query")
def execute_sql(sql: str, db: str = "prod") -> list:
    ...
```

## Custom Params

Control exactly what gets sent to the approval UI:

```python
@protect("deploy", params=lambda service, env="prod", **_: {"service": service, "env": env})
def deploy(service: str, env: str = "prod", dry_run: bool = False) -> str:
    ...
```

## Handling Denials in LLM Feedback Loops

`ActionDeniedException` has a `negotiation` property — a ready-made string you can feed back to the LLM so it can try a different approach instead of crashing:

```python
try:
    delete_file("/etc/hosts")
except ActionDeniedException as e:
    # e.negotiation = "Action 'delete_file' was blocked by Node9: Too dangerous. Choose a different approach."
    response = llm.invoke(e.negotiation)
```

## Framework Examples

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

See [`examples/`](examples/) for full runnable examples.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NODE9_DAEMON_PORT` | `7391` | Daemon port |
| `NODE9_AUTO_START` | — | Set to `1` to auto-launch the daemon if it's not running |
| `NODE9_SKIP` | — | Set to `1` to bypass all checks (unsafe — for tests only) |

## License

Apache-2.0
 
