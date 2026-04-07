"""
node9 — Execution security for Python AI agents.
"""

from ._decorator import protect
from ._exceptions import ActionDeniedException, DaemonNotFoundError
from ._dlp import dlp_scan, safe_path
from ._agent import Node9Agent, tool, internal
from . import _config


def configure(*, agent_name: str = "", policy: str = "") -> None:
    """
    Set agent identity at runtime. Alternative to NODE9_AGENT_NAME / NODE9_AGENT_POLICY env vars.
    Call before the first evaluate() / @protect / agent.dispatch().
    Thread-safe — safe to call from concurrent async frameworks (LangGraph, FastMCP).

    policy values: "audit" | "require_approval" | "block_on_rules" | "" (SaaS default)

    Configuration precedence (highest wins):
      1. configure() called at runtime           — highest priority
      2. Node9Agent.agent_name / .policy class attributes
      3. NODE9_AGENT_NAME / NODE9_AGENT_POLICY env vars  — baseline at import time

    Calling configure() after the first tool call is allowed but not recommended —
    in-flight calls will have already used the previous identity.
    """
    _config.set_identity(agent_name=agent_name, policy=policy)


__all__ = [
    # Core
    "protect",
    "configure",
    # Agent framework
    "Node9Agent",   # base class — subclass and use @tool / @internal
    "tool",         # decorator: governed tool (DLP + audit + policy)
    "internal",     # decorator: infrastructure method (no governance)
    # Node9Agent methods (documented here for IDE discoverability)
    # .build_tools_anthropic() — Anthropic input_schema format
    # .build_tools_openai()    — OpenAI function format
    # .dispatch(name, input)   — route LLM tool call to @tool method
    # .new_session()           — fresh run_id for server/multi-session deployments
    # DLP utilities
    "dlp_scan",
    "safe_path",
    # Exceptions
    "ActionDeniedException",
    "DaemonNotFoundError",
]
__version__ = "2.0.0"
