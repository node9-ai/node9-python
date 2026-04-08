"""Tests for the daemon HTTP client."""
import json
import pytest
from unittest.mock import patch, MagicMock
from http.client import RemoteDisconnected
from urllib.error import URLError
from node9._exceptions import ActionDeniedException, DaemonNotFoundError
from node9._client import evaluate


def test_evaluate_importable_from_public_api():
    """evaluate is in __all__ and importable from the top-level node9 package.

    Note: from node9 import evaluate would succeed even with a broken __all__
    (because __init__.py imports it directly), so we assert __all__ membership
    separately to verify the export is intentional and discoverable by linters
    and import-* consumers.

    Fail-open / offline-mode coverage lives in TestOfflineMode (4 tests), which
    verifies auto-approve behavior, audit log writes, and the require_approval
    RuntimeWarning path.
    """
    import node9
    from node9 import evaluate as pub_evaluate
    assert callable(pub_evaluate)
    assert "evaluate" in node9.__all__


def _make_response(data: dict):
    """Create a mock urllib response."""
    m = MagicMock()
    m.read.return_value = json.dumps(data).encode()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


class TestEvaluate:
    @pytest.fixture(autouse=True)
    def _daemon_up(self):
        """Pretend daemon is reachable so urlopen side_effects go to /check and /wait only."""
        with patch("node9._client._daemon_reachable", return_value=True):
            yield

    def test_allow_decision_passes(self):
        check_resp = _make_response({"id": "req-123"})
        wait_resp = _make_response({"decision": "allow"})

        with patch("urllib.request.urlopen", side_effect=[check_resp, wait_resp]):
            evaluate("write_file", {"path": "/tmp/x"})  # should not raise

    def test_deny_decision_raises(self):
        check_resp = _make_response({"id": "req-123"})
        wait_resp = _make_response({"decision": "deny"})

        with patch("urllib.request.urlopen", side_effect=[check_resp, wait_resp]):
            with pytest.raises(ActionDeniedException) as exc:
                evaluate("bash", {"command": "rm -rf /"})
        assert "bash" in str(exc.value)

    def test_deny_reason_forwarded(self):
        check_resp = _make_response({"id": "req-123"})
        wait_resp = _make_response({"decision": "deny", "reason": "Too dangerous"})

        with patch("urllib.request.urlopen", side_effect=[check_resp, wait_resp]):
            with pytest.raises(ActionDeniedException) as exc:
                evaluate("bash", {"command": "rm -rf /"})
        assert exc.value.reason == "Too dangerous"
        assert "Too dangerous" in exc.value.negotiation

    def test_daemon_not_running_raises(self):
        with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
            with pytest.raises(DaemonNotFoundError) as exc:
                evaluate("write_file", {"path": "/tmp/x"})
        assert "7391" in str(exc.value)
        assert "npx" in str(exc.value)

    def test_remote_disconnected_treated_as_deny(self):
        check_resp = _make_response({"id": "req-123"})

        def side_effect(req, timeout):
            if req.get_method() == "POST":
                return check_resp
            raise RemoteDisconnected("Remote end closed connection without response")

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with pytest.raises(ActionDeniedException):
                evaluate("deploy", {"server": "prod"})

    def test_wait_timeout_treated_as_deny(self):
        check_resp = _make_response({"id": "req-123"})

        def side_effect(req, timeout):
            # First call (POST /check) succeeds, second call (GET /wait) times out
            if req.get_method() == "POST":
                return check_resp
            raise URLError("timed out")

        with patch("urllib.request.urlopen", side_effect=side_effect):
            with pytest.raises(ActionDeniedException):
                evaluate("deploy", {"server": "prod"})

    def test_node9_skip_env_bypasses_daemon(self, monkeypatch):
        # _SKIP is read once at import time — patch the flag directly
        monkeypatch.setattr("node9._client._SKIP", True)
        with patch("urllib.request.urlopen", side_effect=Exception("should not be called")):
            evaluate("anything", {"key": "val"})  # should not raise

    def test_node9_skip_emits_warning_per_call(self, monkeypatch, tmp_path):
        """evaluate() warns on every call when NODE9_SKIP=1 so misuse is visible in logs."""
        import warnings
        monkeypatch.setattr("node9._client._SKIP", True)
        monkeypatch.setenv("HOME", str(tmp_path))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            evaluate("any_tool", {"x": 1})
        assert any("NODE9_SKIP" in str(w.message) for w in caught), \
            "Expected a NODE9_SKIP warning but none was emitted"

    def test_unknown_decision_treated_as_deny(self):
        check_resp = _make_response({"id": "req-123"})
        wait_resp = _make_response({"decision": "unknown_value"})

        with patch("urllib.request.urlopen", side_effect=[check_resp, wait_resp]):
            with pytest.raises(ActionDeniedException):
                evaluate("write_file", {"path": "/tmp/x"})

    def test_sends_correct_tool_name_and_args(self):
        sent_payloads = []
        check_resp = _make_response({"id": "req-abc"})
        wait_resp = _make_response({"decision": "allow"})

        original_urlopen = __import__("urllib.request", fromlist=["urlopen"]).urlopen

        def capturing_urlopen(req, timeout):
            if hasattr(req, "data") and req.data:
                sent_payloads.append(json.loads(req.data))
            if req.get_method() == "POST":
                return check_resp
            return wait_resp

        with patch("urllib.request.urlopen", side_effect=capturing_urlopen):
            evaluate("postgres_query", {"sql": "SELECT 1", "db": "prod"})

        assert len(sent_payloads) == 1
        assert sent_payloads[0]["toolName"] == "postgres_query"
        assert sent_payloads[0]["args"] == {"sql": "SELECT 1", "db": "prod"}

    def test_non_serializable_args_use_str_fallback(self):
        import logging
        check_resp = _make_response({"id": "req-123"})
        wait_resp = _make_response({"decision": "allow"})
        sent_payloads = []

        def capturing_urlopen(req, timeout):
            if hasattr(req, "data") and req.data:
                sent_payloads.append(json.loads(req.data))
            if req.get_method() == "POST":
                return check_resp
            return wait_resp

        logger = logging.getLogger("test")
        with patch("urllib.request.urlopen", side_effect=capturing_urlopen):
            # Should not raise TypeError from json.dumps
            evaluate("tool", {"cmd": "ls", "logger": logger})

        assert sent_payloads[0]["args"]["cmd"] == "ls"
        # Logger was cast to str rather than crashing
        assert isinstance(sent_payloads[0]["args"]["logger"], str)


class TestAutoStart:
    def test_auto_start_not_triggered_by_default(self, monkeypatch, tmp_path):
        """Without NODE9_AUTO_START=1 and no daemon, offline audit mode activates (no crash)."""
        monkeypatch.delenv("NODE9_AUTO_START", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("node9._client._daemon_reachable", return_value=False):
            evaluate("write_file", {"path": "/tmp/x"})  # offline mode — should not raise

    def test_auto_start_triggered_when_env_set(self, monkeypatch):
        """NODE9_AUTO_START=1 calls _auto_start_daemon when daemon is unreachable."""
        monkeypatch.setenv("NODE9_AUTO_START", "1")
        check_resp = _make_response({"id": "req-1"})
        wait_resp = _make_response({"decision": "allow"})
        call_count = {"n": 0}

        def urlopen_side_effect(req, timeout):
            call_count["n"] += 1
            # First call is _daemon_reachable() check → fail
            if call_count["n"] == 1:
                raise URLError("not up")
            # Subsequent calls: POST /check and GET /wait succeed
            if req.get_method() == "POST":
                return check_resp
            return wait_resp

        with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
            with patch("node9._client._auto_start_daemon") as mock_start:
                evaluate("write_file", {"path": "/tmp/x"})
        mock_start.assert_called_once()


class TestAgentIdentityInPayload:
    """Agent name, policy, and run_id are injected into local-daemon payloads."""

    def test_agent_name_in_payload(self, monkeypatch):
        import node9._config as cfg
        monkeypatch.setattr(cfg, "AGENT_NAME", "ci-agent")
        monkeypatch.setattr(cfg, "AGENT_POLICY", "audit")
        sent = []
        check_resp = _make_response({"id": "req-1"})
        wait_resp  = _make_response({"decision": "allow"})

        def capture(req, timeout):
            if hasattr(req, "data") and req.data:
                sent.append(json.loads(req.data))
            return check_resp if req.get_method() == "POST" else wait_resp

        with patch("urllib.request.urlopen", side_effect=capture):
            with patch("node9._client._daemon_reachable", return_value=True):
                evaluate("bash", {"command": "ls"})

        assert sent[0]["agent"] == "ci-agent"

    def test_policy_in_payload(self, monkeypatch):
        import node9._config as cfg
        monkeypatch.setattr(cfg, "AGENT_NAME", "ci-agent")
        monkeypatch.setattr(cfg, "AGENT_POLICY", "audit")
        sent = []
        check_resp = _make_response({"id": "req-1"})
        wait_resp  = _make_response({"decision": "allow"})

        def capture(req, timeout):
            if hasattr(req, "data") and req.data:
                sent.append(json.loads(req.data))
            return check_resp if req.get_method() == "POST" else wait_resp

        with patch("urllib.request.urlopen", side_effect=capture):
            with patch("node9._client._daemon_reachable", return_value=True):
                evaluate("bash", {"command": "ls"})

        assert sent[0]["policy"] == "audit"

    def test_run_id_in_payload(self, monkeypatch):
        import node9._config as cfg
        monkeypatch.setattr(cfg, "AGENT_NAME", "")
        monkeypatch.setattr(cfg, "AGENT_POLICY", "")
        sent = []
        check_resp = _make_response({"id": "req-1"})
        wait_resp  = _make_response({"decision": "allow"})

        def capture(req, timeout):
            if hasattr(req, "data") and req.data:
                sent.append(json.loads(req.data))
            return check_resp if req.get_method() == "POST" else wait_resp

        with patch("urllib.request.urlopen", side_effect=capture):
            with patch("node9._client._daemon_reachable", return_value=True):
                evaluate("bash", {"command": "ls"}, run_id="run-abc-123")

        assert sent[0]["runId"] == "run-abc-123"

    def test_fallback_agent_name_when_empty(self, monkeypatch):
        import node9._config as cfg
        monkeypatch.setattr(cfg, "AGENT_NAME", "")
        monkeypatch.setattr(cfg, "AGENT_POLICY", "")
        sent = []
        check_resp = _make_response({"id": "req-1"})
        wait_resp  = _make_response({"decision": "allow"})

        def capture(req, timeout):
            if hasattr(req, "data") and req.data:
                sent.append(json.loads(req.data))
            return check_resp if req.get_method() == "POST" else wait_resp

        with patch("urllib.request.urlopen", side_effect=capture):
            with patch("node9._client._daemon_reachable", return_value=True):
                evaluate("bash", {"command": "ls"})

        assert sent[0]["agent"] == "Python SDK"


class TestOfflineMode:
    """When neither API key nor daemon is available, offline audit mode activates."""

    def test_offline_mode_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.delenv("NODE9_API_KEY", raising=False)
        monkeypatch.delenv("NODE9_AUTO_START", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("node9._client._daemon_reachable", return_value=False):
            evaluate("bash", {"command": "ls"})  # must not raise

    def test_offline_mode_writes_audit_log(self, monkeypatch, tmp_path):
        import os, json as _json
        monkeypatch.delenv("NODE9_API_KEY", raising=False)
        monkeypatch.delenv("NODE9_AUTO_START", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("node9._client._daemon_reachable", return_value=False):
            evaluate("bash", {"command": "ls"}, run_id="test-run-1")

        audit_path = tmp_path / ".node9" / "audit.log"
        assert audit_path.exists()
        entry = _json.loads(audit_path.read_text().strip())
        assert entry["toolName"] == "bash"
        assert entry["runId"] == "test-run-1"
        assert entry["decision"] == "allow"
        assert entry["mode"] == "offline"

    def test_offline_mode_auto_approves(self, monkeypatch, tmp_path):
        monkeypatch.delenv("NODE9_API_KEY", raising=False)
        monkeypatch.delenv("NODE9_AUTO_START", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch("node9._client._daemon_reachable", return_value=False):
            # Should return normally (not raise ActionDeniedException)
            result = evaluate("bash", {"command": "ls"})
        assert result is None

    def test_offline_with_require_approval_policy_warns(self, monkeypatch, tmp_path):
        """Offline auto-approve must warn loudly when policy is require_approval."""
        import warnings
        import node9._config as cfg
        monkeypatch.delenv("NODE9_API_KEY", raising=False)
        monkeypatch.delenv("NODE9_AUTO_START", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(cfg, "AGENT_POLICY", "require_approval")
        with patch("node9._client._daemon_reachable", return_value=False):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                evaluate("deploy", {"target": "prod"})
        assert any(
            issubclass(w.category, RuntimeWarning) and "require_approval" in str(w.message)
            for w in caught
        ), "Expected RuntimeWarning for offline degradation under require_approval policy"


class TestConfigure:
    def test_configure_sets_agent_name(self):
        from node9 import configure
        import node9._config as cfg
        configure(agent_name="my-agent")
        assert cfg.AGENT_NAME == "my-agent"

    def test_configure_sets_policy(self):
        from node9 import configure
        import node9._config as cfg
        configure(policy="require_approval")
        assert cfg.AGENT_POLICY == "require_approval"

    def test_configure_empty_string_does_not_overwrite(self):
        from node9 import configure
        import node9._config as cfg
        cfg.AGENT_NAME = "existing-agent"
        configure(agent_name="")  # empty → should not overwrite
        assert cfg.AGENT_NAME == "existing-agent"

    def test_configure_both_at_once(self):
        from node9 import configure
        import node9._config as cfg
        configure(agent_name="batch-agent", policy="audit")
        assert cfg.AGENT_NAME == "batch-agent"
        assert cfg.AGENT_POLICY == "audit"
