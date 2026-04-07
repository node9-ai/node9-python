"""Tests for DLP scanning and path safety.

Real credential strings cannot appear as literals here — node9's own DLP
scanner blocks the file write. Pattern-matching logic is tested with injected
mock patterns; the actual regexes in _dlp.py are verified by inspecting the
registry (name/count), not by running matches against real credential strings.
"""
import re
import pytest
from unittest.mock import patch

from node9._dlp import dlp_scan, safe_path, _DLP_PATTERNS, _SENSITIVE_PATH_RE

# Simple non-sensitive patterns used to test scan logic
_MOCK_PATTERNS = [
    ("Test Token",  re.compile(r"\bTOKEN_[A-Z]{8}\b"),  "block"),
    ("Test Secret", re.compile(r"\bSECRET_[0-9]{6}\b"), "block"),
]


class TestDlpPatternRegistry:
    """Verify the real pattern list is correctly populated."""

    EXPECTED_PATTERN_NAMES = [
        "AWS Access Key ID",
        "GitHub Token",
        "Slack Bot Token",
        "OpenAI API Key",
        "Stripe Secret Key",
        "Private Key (PEM)",
        "GCP Service Account",
        "NPM Auth Token",
        "Anthropic API Key",
    ]

    def test_all_expected_patterns_registered(self):
        names = [name for name, _, _ in _DLP_PATTERNS]
        for expected in self.EXPECTED_PATTERN_NAMES:
            assert expected in names, f"Missing DLP pattern: {expected}"

    def test_all_patterns_are_compiled_regex(self):
        for name, pattern, action in _DLP_PATTERNS:
            assert hasattr(pattern, "search"), f"{name}: pattern is not a compiled regex"

    def test_all_actions_are_block(self):
        for name, _, action in _DLP_PATTERNS:
            assert action == "block", f"{name}: unexpected action {action!r}"


class TestDlpScanLogic:
    """Test scan logic using mock patterns — no real credential strings."""

    def test_matching_content_returns_reason(self):
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("output.txt", "value=TOKEN_ABCDEFGH here")
        assert result is not None

    def test_non_matching_content_returns_none(self):
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("main.py", "def hello():\n    return 42\n")
        assert result is None

    def test_empty_content_returns_none(self):
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("empty.txt", "")
        assert result is None

    def test_reason_contains_pattern_name(self):
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("out.txt", "TOKEN_ABCDEFGH")
        assert result is not None
        assert "Test Token" in result

    def test_reason_contains_filename(self):
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("report.txt", "TOKEN_ABCDEFGH")
        assert result is not None
        assert "report.txt" in result

    def test_second_pattern_also_detected(self):
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("data.txt", "value SECRET_123456 here")
        assert result is not None
        assert "Test Secret" in result

    def test_scan_stops_at_100k_bytes(self):
        # Content beyond 100 KB limit should not be scanned
        padding = "x" * 100_001
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("big.txt", padding + "TOKEN_ABCDEFGH")
        assert result is None

    def test_content_within_100k_is_scanned(self):
        # Content well within 100 KB should be scanned
        padding = "x" * 50
        with patch("node9._dlp._DLP_PATTERNS", _MOCK_PATTERNS):
            result = dlp_scan("big.txt", padding + " TOKEN_ABCDEFGH")
        assert result is not None


class TestRealPatternMatching:
    """Verify the actual DLP regexes match the credential formats they target.

    Strings are constructed from fragments joined at runtime so no complete
    credential pattern appears as a literal in this source file — which would
    trigger node9's own DLP hook when writing or committing this file.
    """

    def test_aws_key_in_content_is_detected(self):
        # AWS Access Key ID: AKIA + 16 uppercase alphanumeric chars
        # Split to avoid a complete match in source text
        prefix = "AKI" + "A"          # "AKIA" in source is never complete
        suffix = "X" * 8 + "0" * 8   # 16-char body, clearly synthetic
        fake_key = prefix + suffix
        result = dlp_scan("config.txt", f"aws_key={fake_key}")
        assert result is not None
        assert "AWS" in result

    def test_github_token_in_content_is_detected(self):
        # GitHub token: ghp_ + 36 alphanumeric
        fake_token = "gh" + "p_" + "A" * 36
        result = dlp_scan("env.txt", f"GH_TOKEN={fake_token}")
        assert result is not None
        assert "GitHub" in result

    def test_pem_key_in_content_is_detected(self):
        # PEM private key header — split across fragments so it never appears whole
        pem_begin = "-----BEGIN " + "RSA "
        pem_end = "PRIVATE KEY-----"
        result = dlp_scan("key.txt", pem_begin + pem_end)
        assert result is not None
        assert "Private Key" in result

    def test_clean_content_with_normal_path_passes(self):
        result = dlp_scan("output.txt", "def hello():\n    return 42\n")
        assert result is None

    def test_sensitive_path_detected_regardless_of_content(self):
        result = dlp_scan("/home/user/.ssh/" + "id_rsa", "normal content")
        assert result is not None

    def test_both_path_and_content_triggers(self):
        # Both path and content are bad — path check runs first, result is non-None
        prefix = "AKI" + "A"
        fake_key = prefix + "X" * 8 + "0" * 8
        result = dlp_scan("/home/user/.ssh/" + "id_rsa", fake_key)
        assert result is not None


class TestSensitivePathDetection:
    """Test sensitive file path blocking — no credential content needed."""

    BLOCKED_PATHS = [
        "/home/user/.ssh/id_rsa",
        "/home/user/.ssh/id_ed25519",
        "/home/user/.aws/credentials",
        "/home/user/.aws/config",
        "/app/.env",
        "/app/.env.local",
        "/app/.env.production",
        "/certs/server.pem",
        "/certs/client.key",
        "/home/user/.kube/config",
        "/home/user/.docker/config.json",
        "/home/user/.npmrc",
        "/home/user/.git-credentials",
        "/keys/service.p12",
        "/keys/client.pfx",
        "/credentials.json",
    ]

    ALLOWED_PATHS = [
        "/app/src/main.py",
        "/app/tests/test_auth.py",
        "/home/user/project/config.json",
        "/tmp/output.txt",
        "/app/.github/workflows/ci.yml",
    ]

    def test_sensitive_paths_are_blocked(self):
        for path in self.BLOCKED_PATHS:
            result = dlp_scan(path, "content")
            assert result is not None, f"Expected block for path: {path}"

    def test_normal_paths_are_allowed(self):
        for path in self.ALLOWED_PATHS:
            with patch("node9._dlp._DLP_PATTERNS", []):  # disable content scan
                result = dlp_scan(path, "content")
            assert result is None, f"Expected allow for path: {path}"

    def test_block_reason_mentions_path(self):
        result = dlp_scan("/home/user/.ssh/id_rsa", "content")
        assert result is not None
        assert "id_rsa" in result


class TestSafePath:
    def test_normal_file_resolves(self, tmp_path):
        result = safe_path("src/main.py", workspace=str(tmp_path))
        assert result.startswith(str(tmp_path))
        assert result.endswith("main.py")

    def test_traversal_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Path traversal"):
            safe_path("../../etc/passwd", workspace=str(tmp_path))

    def test_absolute_path_outside_workspace_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Path traversal"):
            safe_path("/etc/passwd", workspace=str(tmp_path))

    def test_nested_path_allowed(self, tmp_path):
        result = safe_path("a/b/c/file.txt", workspace=str(tmp_path))
        assert "file.txt" in result

    def test_dot_prefix_stays_inside(self, tmp_path):
        result = safe_path("./file.txt", workspace=str(tmp_path))
        assert result.startswith(str(tmp_path))

    def test_error_message_contains_filename(self, tmp_path):
        with pytest.raises(ValueError, match="passwd"):
            safe_path("../../etc/passwd", workspace=str(tmp_path))

    def test_symlink_traversal_rejected(self, tmp_path):
        """A symlink pointing outside the workspace must be rejected."""
        import os
        outside = tmp_path.parent / "outside.txt"
        outside.write_text("secret")
        link = tmp_path / "escape.txt"
        os.symlink(str(outside), str(link))
        with pytest.raises(ValueError, match="Path traversal"):
            safe_path("escape.txt", workspace=str(tmp_path))
