import os

DAEMON_PORT  = int(os.environ.get("NODE9_DAEMON_PORT", "7391"))
AGENT_NAME   = os.environ.get("NODE9_AGENT_NAME", "")
# audit | require_approval | block_on_rules | "" (empty = default SaaS behaviour)
AGENT_POLICY = os.environ.get("NODE9_AGENT_POLICY", "")
