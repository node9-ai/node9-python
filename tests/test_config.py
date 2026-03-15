"""Tests for daemon port configuration."""
import importlib
import pytest


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
