class ActionDeniedException(Exception):
    """Raised when Node9 blocks an agent action."""

    def __init__(self, tool_name: str, reason: str = "Denied by Node9 policy"):
        self.tool_name = tool_name
        self.reason = reason
        # negotiation: ready-made string for feeding back to the LLM
        self.negotiation = f"Action '{tool_name}' was blocked by Node9: {reason}. Choose a different approach."
        super().__init__(f"[Node9] Action '{tool_name}' was blocked: {reason}")


class DaemonNotFoundError(Exception):
    """Raised when the Node9 daemon is not reachable."""

    def __init__(self, port: int = 7391):
        super().__init__(
            f"Node9 daemon not found on localhost:{port}.\n"
            f"To enable execution security, run:\n"
            f"  npx @node9/proxy daemon\n"
            f"or set NODE9_SKIP=1 to bypass (unsafe)."
        )
