"""
CrewAI integration — secure any tool function with @protect.

Install:
  pip install node9 crewai

Run the Node9 daemon first:
  npx @node9/proxy daemon
"""

from node9 import protect, ActionDeniedException
from crewai import Agent, Task, Crew
from crewai.tools import tool


# --- Decorate CrewAI @tool functions directly ---

@tool("write_file")
@protect("write_file")
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    with open(path, "w") as f:
        f.write(content)
    return f"Written to {path}"


_ALLOWED_COMMANDS = {"pytest", "ruff check .", "mypy src/"}

@tool("run_shell")
@protect("bash")
def run_shell(command: str) -> str:
    """Execute an allowlisted shell command."""
    import shlex, subprocess
    # Allowlist-only: never pass LLM-controlled strings to shell=True.
    if command not in _ALLOWED_COMMANDS:
        raise ValueError(f"Command {command!r} not in allowed list")
    return subprocess.check_output(shlex.split(command), text=True)


@tool("deploy_service")
@protect("deploy")
def deploy_service(service: str, environment: str = "production") -> str:
    """Deploy a service to an environment."""
    # your real deploy logic here
    return f"Deployed {service} to {environment}"


# --- Build the crew ---

def build_crew() -> Crew:
    engineer = Agent(
        role="Software Engineer",
        goal="Complete coding tasks safely",
        backstory="An AI engineer that always asks for approval before risky actions.",
        tools=[write_file, run_shell, deploy_service],
        verbose=True,
    )

    task = Task(
        description="Write a health check script to /tmp/healthcheck.sh and deploy the api service to staging.",
        expected_output="Confirmation that the script was written and the service deployed.",
        agent=engineer,
    )

    return Crew(agents=[engineer], tasks=[task], verbose=True)


if __name__ == "__main__":
    crew = build_crew()
    try:
        result = crew.kickoff()
        print(result)
    except ActionDeniedException as e:
        print(f"Node9 blocked the action: {e}")
