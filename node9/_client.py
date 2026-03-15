"""
Thin HTTP client — talks to the local Node9 daemon on localhost:7391.

Flow:
  POST /check  → { id }                      registers the action
  GET  /wait/:id → { decision, reason? }     blocks until approved / denied
"""

import json
import os
import shutil
import subprocess
import time
import http.client
import urllib.error
import urllib.request
from typing import Any

from ._config import DAEMON_PORT
from ._exceptions import ActionDeniedException, DaemonNotFoundError

_DAEMON_BASE = f"http://127.0.0.1:{DAEMON_PORT}"
# The daemon auto-denies after ~55s; we wait slightly longer to get that response.
_CHECK_TIMEOUT = 5      # seconds to establish connection
_WAIT_TIMEOUT = 65      # seconds to wait for human decision


def _daemon_reachable() -> bool:
    try:
        req = urllib.request.Request(f"{_DAEMON_BASE}/settings", method="GET")
        with urllib.request.urlopen(req, timeout=1.0):
            return True
    except urllib.error.URLError:
        return False


def _auto_start_daemon() -> None:
    """Opt-in: start the daemon in the background when NODE9_AUTO_START=1."""
    if shutil.which("node9"):
        cmd = ["node9", "daemon"]
    elif shutil.which("npx"):
        cmd = ["npx", "@node9/proxy", "daemon"]
    else:
        raise DaemonNotFoundError(DAEMON_PORT)
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(10):
        time.sleep(0.5)
        if _daemon_reachable():
            return
    raise DaemonNotFoundError(DAEMON_PORT)


def _post(path: str, payload: dict) -> dict:
    # default=str: safely serialize non-JSON-native objects (loggers, datetimes, etc.)
    data = json.dumps(payload, default=str).encode()
    req = urllib.request.Request(
        f"{_DAEMON_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        raise DaemonNotFoundError(DAEMON_PORT)


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{_DAEMON_BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_WAIT_TIMEOUT) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, http.client.HTTPException):
        # URLError = timeout / connection error
        # HTTPException (incl. RemoteDisconnected) = daemon closed connection → treat as deny
        return {"decision": "deny", "reason": "Node9 daemon connection timed out or closed."}


def evaluate(tool_name: str, args: dict[str, Any]) -> None:
    """
    Sends the action to the daemon and blocks until a decision is made.
    Raises ActionDeniedException if the action is denied.
    Does nothing if NODE9_SKIP=1 is set (unsafe bypass for testing).
    Set NODE9_AUTO_START=1 to automatically launch the daemon if it's not running.
    """
    if os.environ.get("NODE9_SKIP") == "1":
        return

    if os.environ.get("NODE9_AUTO_START") == "1" and not _daemon_reachable():
        _auto_start_daemon()

    result = _post("/check", {"toolName": tool_name, "args": args, "cwd": os.getcwd(), "agent": "Python SDK"})
    request_id = result.get("id")
    if not request_id:
        raise RuntimeError(f"[Node9] Unexpected daemon response: {result}")

    print(f"🛡️  Node9: waiting for approval of '{tool_name}'...", flush=True)
    decision_result = _get(f"/wait/{request_id}")
    decision = decision_result.get("decision", "deny")

    if decision != "allow":
        reason = decision_result.get("reason", "Denied by Node9 policy")
        raise ActionDeniedException(tool_name, reason)
