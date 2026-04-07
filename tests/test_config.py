"""Tests for daemon port configuration and configure() behaviour."""
import importlib
import pytest

from node9 import configure
import node9._config as cfg


class TestConfigure:
    def test_configure_sets_agent_name(self):
        configure(agent_name="test-agent", policy="")
        assert cfg.AGENT_NAME == "test-agent"

    def test_configure_sets_policy(self):
        configure(agent_name="", policy="audit")
        assert cfg.AGENT_POLICY == "audit"

    def test_configure_called_twice_second_wins(self):
        configure(agent_name="first", policy="audit")
        configure(agent_name="second", policy="require_approval")
        assert cfg.AGENT_NAME == "second"
        assert cfg.AGENT_POLICY == "require_approval"

    def test_configure_empty_string_does_not_overwrite(self):
        configure(agent_name="kept", policy="audit")
        configure(agent_name="", policy="")  # empty args should not clear existing values
        assert cfg.AGENT_NAME == "kept"
        assert cfg.AGENT_POLICY == "audit"

    def test_configure_wins_over_env_var(self, monkeypatch):
        """configure() called after import overrides env var defaults."""
        monkeypatch.setenv("NODE9_AGENT_NAME", "env-agent")
        importlib.reload(cfg)
        assert cfg.AGENT_NAME == "env-agent"
        configure(agent_name="runtime-agent")
        assert cfg.AGENT_NAME == "runtime-agent"

    def test_env_var_is_baseline_before_configure(self, monkeypatch):
        """Without configure(), env var sets the identity."""
        monkeypatch.setenv("NODE9_AGENT_NAME", "from-env")
        monkeypatch.setenv("NODE9_AGENT_POLICY", "require_approval")
        importlib.reload(cfg)
        assert cfg.AGENT_NAME == "from-env"
        assert cfg.AGENT_POLICY == "require_approval"


class TestDaemonPort:
    def test_default_port(self, monkeypatch):
        monkeypatch.delenv("NODE9_DAEMON_PORT", raising=False)
        import node9._config as cfg
        importlib.reload(cfg)
        assert cfg.DAEMON_PORT == 7391

    def test_env_var_overrides_port(self, monkeypatch):
        monkeypatch.setenv("NODE9_DAEMON_PORT", "8000")
        import node9._config as cfg
        importlib.reload(cfg)
        assert cfg.DAEMON_PORT == 8000

    def test_port_is_int(self, monkeypatch):
        monkeypatch.delenv("NODE9_DAEMON_PORT", raising=False)
        import node9._config as cfg
        importlib.reload(cfg)
        assert isinstance(cfg.DAEMON_PORT, int)
