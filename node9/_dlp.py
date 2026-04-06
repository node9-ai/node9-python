"""
DLP (Data Loss Prevention) and path safety — single source of truth.

Used by Node9Agent's @tool decorator automatically.
Can also be imported directly: from node9 import dlp_scan, safe_path
"""

import os
import re

_DLP_PATTERNS = [
    ("AWS Access Key ID",     re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                           "block"),
    ("GitHub Token",          re.compile(r"\bgh[pous]_[A-Za-z0-9]{36}\b"),                   "block"),
    ("Slack Bot Token",       re.compile(r"\bxoxb-[0-9A-Za-z-]{20,100}\b"),                  "block"),
    ("OpenAI API Key",        re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}\b"),                      "block"),
    ("Stripe Secret Key",     re.compile(r"\bsk_(?:live|test)_[0-9a-zA-Z]{24}\b"),           "block"),
    ("Private Key (PEM)",     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "block"),
    ("GCP Service Account",   re.compile(r'"type"\s*:\s*"service_account"'),                  "block"),
    ("NPM Auth Token",        re.compile(r"_authToken\s*=\s*[A-Za-z0-9_\-]{20,}"),           "block"),
    ("Anthropic API Key",     re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),                  "block"),
]

_SENSITIVE_PATH_RE = re.compile(
    r"([\\/]\.ssh[\\/]|[\\/]\.aws[\\/]|[\\/]\.config[\\/]gcloud[\\/]"
    r"|[\\/]\.azure[\\/]|[\\/]\.kube[\\/]config$|[\\/]\.env(\.|$)"
    r"|[\\/]\.git-credentials$|[\\/]\.npmrc$|[\\/]\.docker[\\/]config\.json$"
    r"|[\\/][^/\\]+\.(pem|key|p12|pfx)$|[\\/]credentials\.json$"
    r"|[\\/]id_(rsa|ed25519|ecdsa)$)",
    re.IGNORECASE,
)

_SCAN_LIMIT_BYTES = 100_000


def dlp_scan(filename: str, content: str) -> str | None:
    """
    Returns a human-readable block reason if a secret is detected, None if clean.
    Checks sensitive file paths first, then scans content for known secret patterns.
    """
    normalized = filename.replace("\\", "/")
    if _SENSITIVE_PATH_RE.search(normalized):
        return f"sensitive file path blocked: {filename}"

    text = content[:_SCAN_LIMIT_BYTES]
    for name, pattern, _ in _DLP_PATTERNS:
        if pattern.search(text):
            return f"{name} detected in {filename}"

    return None


def safe_path(filename: str, workspace: str) -> str:
    """
    Resolve filename relative to workspace and verify it stays inside.
    Raises ValueError on path traversal attempts.
    """
    resolved = os.path.realpath(os.path.join(workspace, filename))
    workspace_root = os.path.realpath(workspace) + os.sep
    if not resolved.startswith(workspace_root):
        raise ValueError(f"Path traversal rejected: {filename!r} escapes workspace")
    return resolved
