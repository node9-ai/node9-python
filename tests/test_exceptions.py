"""Tests for exception messages and attributes."""
from node9._exceptions import ActionDeniedException, DaemonNotFoundError


class TestActionDeniedException:
    def test_message_contains_tool_name(self):
        exc = ActionDeniedException("bash")
        assert "bash" in str(exc)

    def test_message_contains_reason(self):
        exc = ActionDeniedException("write_file", reason="Denied by admin")
        assert "Denied by admin" in str(exc)

    def test_default_reason(self):
        exc = ActionDeniedException("deploy")
        assert "policy" in str(exc).lower()

    def test_attributes(self):
        exc = ActionDeniedException("bash", reason="blocked")
        assert exc.tool_name == "bash"
        assert exc.reason == "blocked"

    def test_is_exception(self):
        assert isinstance(ActionDeniedException("x"), Exception)

    def test_negotiation_property_present(self):
        exc = ActionDeniedException("bash", reason="Not allowed at this time")
        assert hasattr(exc, "negotiation")
        assert "bash" in exc.negotiation
        assert "Not allowed at this time" in exc.negotiation

    def test_negotiation_default_reason(self):
        exc = ActionDeniedException("deploy")
        assert "deploy" in exc.negotiation


class TestDaemonNotFoundError:
    def test_contains_port(self):
        exc = DaemonNotFoundError(7391)
        assert "7391" in str(exc)

    def test_contains_actionable_hint(self):
        exc = DaemonNotFoundError()
        msg = str(exc)
        assert "npx" in msg or "node9" in msg

    def test_default_port(self):
        exc = DaemonNotFoundError()
        assert "7391" in str(exc)
