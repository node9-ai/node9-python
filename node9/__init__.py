"""
node9 — Execution security for Python AI agents.

Quick start:
    from node9 import protect

    @protect("write_file")
    def write_file(path: str, content: str):
        ...

    @protect("bash")
    def run_shell(cmd: str):
        ...
"""

from ._decorator import protect
from ._exceptions import ActionDeniedException, DaemonNotFoundError

__all__ = ["protect", "ActionDeniedException", "DaemonNotFoundError"]
__version__ = "0.1.0"
