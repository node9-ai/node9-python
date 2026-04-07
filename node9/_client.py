"""
Thin HTTP client — talks to either the local Node9 daemon or node9 SaaS.

Routing:
  NODE9_API_KEY set    → node9 SaaS (api.node9.ai)      cloud / CI
  daemon reachable     → local proxy (localhost:7391)    persona 1 / local dev
  neither              → offline audit log               dev / test, never blocks
"""

import json
import os
import platform
import re
import shutil
import subprocess
import time
import http.client
import urllib.error
import urllib.request
from typing import Any

from . import _config
from ._config import DAEMON_PORT
from ._exceptions import ActionDeniedException, DaemonNotFoundError

_DAEMON_BASE = f"http://127.0.0.1:{DAEMON_PORT}"
# The daemon auto-denies after ~55s; we wait slightly longer to get that response.
_CHECK_TIMEOUT = 5      # seconds to establish connection
_WAIT_TIMEOUT = 65      # seconds to wait for human decision

_SKIP = os.environ.get("NODE9_SKIP") == "1"

_CI_CONTEXT_MAX_BYTES = 10_000
_CI_CONTEXT_ALLOWED_KEYS = {
    "tests_after", "files_changed", "issues_found", "issues_fixed",
    "github_repository", "github_head_ref", "iteration",
    "draft_pr_number", "draft_pr_url",
}
_REQUEST_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,128}$')


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


def _read_ci_context() -> dict | None:
    """Read ~/.node9/ci-context.json if present (written by the CI agent before git push).
    Size-capped and key-allowlisted so an attacker-controlled file cannot poison the payload."""
    ci_context_path = os.path.join(os.path.expanduser("~"), ".node9", "ci-context.json")
    try:
        with open(ci_context_path, "rb") as f:
            raw_bytes = f.read(_CI_CONTEXT_MAX_BYTES + 1)
        if len(raw_bytes) > _CI_CONTEXT_MAX_BYTES:
            return None
        raw = json.loads(raw_bytes)
        if not isinstance(raw, dict):
            return None
        return {k: v for k, v in raw.items() if k in _CI_CONTEXT_ALLOWED_KEYS}
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _offline_audit(tool_name: str, args: dict[str, Any], run_id: str) -> None:
    """
    Offline audit mode — no daemon, no SaaS.
    Writes a local audit entry and auto-approves. Never blocks.
    Used when neither NODE9_API_KEY nor local daemon is available.
    """
    import datetime
    audit_dir = os.path.join(os.path.expanduser("~"), ".node9")
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, "audit.log")
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "mode": "offline",
        "agent": (_config.get()[0] or "Python SDK"),
        "policy": (_config.get()[1] or "offline"),
        "runId": run_id,
        "toolName": tool_name,
        "args": args,
        "decision": "allow",
    }
    try:
        with open(audit_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass  # never crash the agent due to audit failure
    print(f"  [node9 offline] {tool_name} — logged to {audit_path}", flush=True)


def _evaluate_cloud(tool_name: str, args: dict[str, Any], run_id: str = "") -> None:
    """
    Cloud routing: POST directly to node9 SaaS when NODE9_API_KEY is set.
    Used in CI environments where the local daemon is not running.
    """
    api_key = os.environ.get("NODE9_API_KEY", "")
    if not api_key:
        raise RuntimeError("[Node9] NODE9_API_KEY is set but empty — cannot authenticate.")

    api_url = os.environ.get("NODE9_API_URL", "https://api.node9.ai/api/v1/intercept").rstrip("/")

    if not api_url.startswith("https://") and not api_url.startswith("http://localhost"):
        raise RuntimeError(
            f"[Node9] NODE9_API_URL must use HTTPS to protect credentials (got: {api_url!r})"
        )

    _agent_name, _agent_policy = _config.get()
    payload: dict = {
        "toolName": tool_name,
        "args": args,
        "agentName": _agent_name or "Python SDK",
        "policy": _agent_policy,
        "runId": run_id,
        "context": {
            "agent": _agent_name or "Python SDK",
            "hostname": platform.node(),
            "platform": platform.system().lower(),
            "cwd": os.getcwd(),
        },
    }

    ci_context = _read_ci_context()
    if ci_context:
        payload["ciContext"] = ci_context

    data = json.dumps(payload, default=str).encode()
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise RuntimeError(
            f"[Node9] SaaS returned HTTP {e.code} {e.reason} — body: {body}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"[Node9] Failed to reach node9 SaaS: {e}") from e

    if result.get("approved"):
        return

    if not result.get("pending"):
        reason = result.get("reason", "Denied by Node9 policy")
        raise ActionDeniedException(tool_name, reason)

    request_id = result.get("requestId")
    if not request_id:
        raise RuntimeError(f"[Node9] Unexpected SaaS response: {result}")
    if not _REQUEST_ID_RE.match(str(request_id)):
        raise RuntimeError(f"[Node9] Invalid requestId format: {request_id!r}")

    print(f"🛡️  Node9: waiting for approval of '{tool_name}'...", flush=True)

    poll_timeout = max(30, min(3600, int(os.environ.get("NODE9_CLOUD_TIMEOUT", "600"))))
    status_url = f"{api_url}/status/{request_id}"
    poll_deadline = time.time() + poll_timeout

    while time.time() < poll_deadline:
        time.sleep(1)
        try:
            poll_req = urllib.request.Request(
                status_url,
                headers={"Authorization": f"Bearer {api_key}"},
                method="GET",
            )
            with urllib.request.urlopen(poll_req, timeout=5) as resp:
                status_result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError(
                    f"[Node9] Authentication failed during polling (HTTP {e.code}) — check NODE9_API_KEY."
                ) from e
            continue
        except (urllib.error.URLError, http.client.HTTPException):
            continue

        status = status_result.get("status", "").upper()
        if status == "APPROVED":
            return
        if status in ("DENIED", "AUTO_BLOCKED", "TIMED_OUT", "FIX"):
            reason = status_result.get("reason", "Denied by Node9 policy")
            raise ActionDeniedException(tool_name, reason)

    raise ActionDeniedException(tool_name, f"Cloud approval timed out after {poll_timeout}s.")


def evaluate(tool_name: str, args: dict[str, Any], *, run_id: str = "") -> None:
    """
    Sends the action to node9 for audit / approval. Routing:
      NODE9_SKIP=1        → no-op (unsafe bypass for testing)
      NODE9_API_KEY set   → node9 SaaS
      daemon reachable    → local proxy
      neither             → offline audit log (auto-approve, never blocks)

    Raises ActionDeniedException if the action is denied.
    """
    if _SKIP:
        import warnings
        warnings.warn(
            f"[Node9] NODE9_SKIP=1 — governance bypassed for '{tool_name}'. "
            "Do not use in production.",
            stacklevel=3,
        )
        _offline_audit(tool_name, {**args, "_skip": True}, run_id=run_id)
        return

    if os.environ.get("NODE9_API_KEY"):
        _evaluate_cloud(tool_name, args, run_id=run_id)
        return

    if os.environ.get("NODE9_AUTO_START") == "1" and not _daemon_reachable():
        _auto_start_daemon()

    if not _daemon_reachable():
        _offline_audit(tool_name, args, run_id=run_id)
        return

    result = _post("/check", {
        "toolName": tool_name,
        "args": args,
        "cwd": os.getcwd(),
        "agent": (_config.get()[0] or "Python SDK"),
        "policy": _config.get()[1],
        "runId": run_id,
    })
    request_id = result.get("id")
    if not request_id:
        raise RuntimeError(f"[Node9] Unexpected daemon response: {result}")

    print(f"🛡️  Node9: waiting for approval of '{tool_name}'...", flush=True)
    decision_result = _get(f"/wait/{request_id}")
    decision = decision_result.get("decision", "deny")

    if decision != "allow":
        reason = decision_result.get("reason", "Denied by Node9 policy")
        raise ActionDeniedException(tool_name, reason)
