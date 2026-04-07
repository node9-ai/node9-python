"""
node9 — Execution security for Python AI agents.
"""

import threading

from ._decorator import protect
from ._exceptions import ActionDeniedException, DaemonNotFoundError
from ._dlp import dlp_scan, safe_path
from ._agent import Node9Agent, tool, internal
from . import _config

_configure_lock = threading.Lock()


def configure(*, agent_name: str = "", policy: str = "") -> None:
    """
    Set agent identity at runtime. Alternative to NODE9_AGENT_NAME / NODE9_AGENT_POLICY env vars.
    Call before the first evaluate() / @protect / agent.dispatch().
    Thread-safe — safe to call from concurrent async frameworks (LangGraph, FastMCP).

    policy values: "audit" | "require_approval" | "block_on_rules" | "" (SaaS default)
    """
    with _configure_lock:
        if agent_name:
            _config.AGENT_NAME = agent_name
        if policy:
            _config.AGENT_POLICY = policy


__all__ = [
    # Core
    "protect",
    "configure",
    # Agent framework
    "Node9Agent",
    "tool",
    "internal",
    # DLP utilities
    "dlp_scan",
    "safe_path",
    # Exceptions
    "ActionDeniedException",
    "DaemonNotFoundError",
]
__version__ = "2.0.0"
