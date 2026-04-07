"""
Basic usage — plain Python functions.

Run the Node9 daemon first:
  npx @node9/proxy daemon

Then run this file:
  python examples/basic.py
"""

from node9 import protect, ActionDeniedException, DaemonNotFoundError


# --- Auto-capture: no config needed, all args are sent automatically ---

@protect
def write_file(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)
    print(f"Written: {path}")


@protect
def delete_file(path: str) -> None:
    import os
    os.remove(path)
    print(f"Deleted: {path}")


_ALLOWED_COMMANDS = {"ls", "pwd", "git status", "git log --oneline"}

@protect("bash")
def run_shell(command: str) -> str:
    import shlex, subprocess
    # Allowlist-only: never pass LLM-controlled strings to shell=True.
    if command not in _ALLOWED_COMMANDS:
        raise ValueError(f"Command {command!r} not in allowed list")
    return subprocess.check_output(shlex.split(command), text=True)


# --- Custom tool name + params lambda ---

@protect("postgres_query", params=lambda sql, db="prod", **_: {"sql": sql, "database": db})
def execute_sql(sql: str, db: str = "prod") -> list:
    # your real DB call here
    print(f"Executing on {db}: {sql}")
    return []


if __name__ == "__main__":
    try:
        # This will open a Node9 approval popup / Slack request
        write_file("/tmp/node9-test.txt", "Hello from node9!")
        print("Approved! File written.")
    except ActionDeniedException as e:
        print(f"Blocked: {e}")
    except DaemonNotFoundError as e:
        print(f"Error: {e}")
