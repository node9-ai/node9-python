"""Tests for the daemon HTTP client."""
import json
import pytest
from unittest.mock import patch, MagicMock
from http.client import RemoteDisconnected
from urllib.error import URLError
from node9._exceptions import ActionDeniedException, DaemonNotFoundError
from node9._client import evaluate


def _make_response(data: dict):
    """Create a mock urllib response."""
    m = MagicMock()
    m.read.return_value = json.dumps(data).encode()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


class TestEvaluate:
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
        monkeypatch.setenv("NODE9_SKIP", "1")
        # No mock needed — should not call urlopen at all
        with patch("urllib.request.urlopen", side_effect=Exception("should not be called")):
            evaluate("anything", {"key": "val"})  # should not raise

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
    def test_auto_start_not_triggered_by_default(self, monkeypatch):
        """Without NODE9_AUTO_START=1, DaemonNotFoundError is raised immediately."""
        monkeypatch.delenv("NODE9_AUTO_START", raising=False)
        with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
            with pytest.raises(DaemonNotFoundError):
                evaluate("write_file", {"path": "/tmp/x"})

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
