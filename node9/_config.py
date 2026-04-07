import os
import threading

DAEMON_PORT  = int(os.environ.get("NODE9_DAEMON_PORT", "7391"))
AGENT_NAME   = os.environ.get("NODE9_AGENT_NAME", "")
# audit | require_approval | block_on_rules | "" (empty = default SaaS behaviour)
AGENT_POLICY = os.environ.get("NODE9_AGENT_POLICY", "")

_lock = threading.RLock()


def get() -> tuple[str, str]:
    """Thread-safe snapshot of (AGENT_NAME, AGENT_POLICY)."""
    with _lock:
        return AGENT_NAME, AGENT_POLICY


def set_identity(*, agent_name: str = "", policy: str = "") -> None:
    """Thread-safe write. Called by node9.configure() and Node9Agent.__init__."""
    global AGENT_NAME, AGENT_POLICY
    with _lock:
        if agent_name:
            AGENT_NAME = agent_name
        if policy:
            AGENT_POLICY = policy
