import asyncio
import pytest
from unittest.mock import patch
from node9 import protect, ActionDeniedException


@protect
def write_file(path: str, content: str = ""):
    return f"written:{path}"

@protect("bash")
def run_shell(cmd: str):
    return f"ran:{cmd}"

@protect("deploy", params=lambda server, env="prod", **_: {"server": server, "env": env})
def deploy(server: str, env: str = "prod"):
    return f"deployed:{server}"


PATCH = "node9._decorator.evaluate"


class TestProtectDecorator:
    def test_allow_passes_through(self):
        with patch(PATCH, return_value=None):
            result = write_file("/tmp/test.txt", "hello")
        assert result == "written:/tmp/test.txt"

    def test_deny_raises_exception(self):
        with patch(PATCH, side_effect=ActionDeniedException("write_file")):
            with pytest.raises(ActionDeniedException) as exc:
                write_file("/tmp/test.txt")
        assert "write_file" in str(exc.value)

    def test_auto_captures_args(self):
        captured = {}
        def spy(tool_name, args):
            captured.update(args)
        with patch(PATCH, side_effect=spy):
            write_file("/etc/passwd", content="bad")
        assert captured == {"path": "/etc/passwd", "content": "bad"}

    def test_auto_captures_defaults(self):
        captured = {}
        def spy(tool_name, args):
            captured.update(args)
        with patch(PATCH, side_effect=spy):
            write_file("/tmp/x")
        assert captured["content"] == ""

    def test_custom_tool_name(self):
        names = []
        def spy(tool_name, args):
            names.append(tool_name)
        with patch(PATCH, side_effect=spy):
            run_shell("ls -la")
        assert names == ["bash"]

    def test_params_lambda(self):
        captured = {}
        def spy(tool_name, args):
            captured.update(args)
        with patch(PATCH, side_effect=spy):
            deploy("web-01", env="staging")
        assert captured == {"server": "web-01", "env": "staging"}

    def test_no_args_decorator_uses_func_name(self):
        names = []
        def spy(tool_name, args):
            names.append(tool_name)

        @protect
        def my_tool(x: int):
            pass

        with patch(PATCH, side_effect=spy):
            my_tool(42)
        assert names == ["my_tool"]

    def test_node9_skip_bypasses(self, monkeypatch):
        monkeypatch.setenv("NODE9_SKIP", "1")
        result = write_file("/tmp/skipped.txt")
        assert result == "written:/tmp/skipped.txt"

    def test_return_value_preserved(self):
        with patch(PATCH, return_value=None):
            assert run_shell("echo hi") == "ran:echo hi"


class TestProtectEdgeCases:
    def test_kwargs_only_function(self):
        captured = {}
        def spy(tool_name, args):
            captured.update(args)

        @protect("kw_tool")
        def kw_only(*, host: str, port: int = 5432):
            pass

        with patch(PATCH, side_effect=spy):
            kw_only(host="localhost", port=3306)
        assert captured == {"host": "localhost", "port": 3306}

    def test_class_method(self):
        names = []
        def spy(tool_name, args):
            names.append(tool_name)

        class MyAgent:
            @protect("agent_action")
            def take_action(self, action: str):
                return action

        agent = MyAgent()
        with patch(PATCH, side_effect=spy):
            agent.take_action("deploy")
        assert names == ["agent_action"]

    def test_preserves_function_metadata(self):
        @protect("my_tool")
        def documented_function(x: int) -> str:
            """This is my docstring."""
            return str(x)

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is my docstring."

    def test_exception_propagates_from_wrapped_function(self):
        @protect("failing_tool")
        def always_fails():
            raise ValueError("internal error")

        with patch(PATCH, return_value=None):
            with pytest.raises(ValueError, match="internal error"):
                always_fails()

    def test_mixed_positional_and_keyword_args(self):
        captured = {}
        def spy(tool_name, args):
            captured.update(args)

        @protect("mixed")
        def mixed(a: str, b: int, c: str = "default"):
            pass

        with patch(PATCH, side_effect=spy):
            mixed("hello", 42, c="override")
        assert captured == {"a": "hello", "b": 42, "c": "override"}


class TestProtectAsync:
    def test_async_function_allowed(self):
        @protect("async_write")
        async def async_write(path: str) -> str:
            return f"written:{path}"

        with patch(PATCH, return_value=None):
            result = asyncio.run(async_write("/tmp/test.txt"))
        assert result == "written:/tmp/test.txt"

    def test_async_function_denied(self):
        @protect("async_bash")
        async def async_bash(cmd: str) -> str:
            return f"ran:{cmd}"

        with patch(PATCH, side_effect=ActionDeniedException("async_bash")):
            with pytest.raises(ActionDeniedException) as exc:
                asyncio.run(async_bash("rm -rf /"))
        assert "async_bash" in str(exc.value)

    def test_async_auto_captures_args(self):
        captured = {}
        def spy(tool_name, args):
            captured.update(args)

        @protect("async_tool")
        async def async_tool(path: str, content: str = "default") -> None:
            pass

        with patch(PATCH, side_effect=spy):
            asyncio.run(async_tool("/tmp/x", content="hello"))
        assert captured == {"path": "/tmp/x", "content": "hello"}

    def test_async_preserves_return_value(self):
        @protect
        async def fetch_data(url: str) -> dict:
            return {"url": url, "data": "result"}

        with patch(PATCH, return_value=None):
            result = asyncio.run(fetch_data("https://example.com"))
        assert result == {"url": "https://example.com", "data": "result"}

    def test_async_preserves_metadata(self):
        @protect("my_async_tool")
        async def documented_async(x: int) -> str:
            """Async docstring."""
            return str(x)

        assert documented_async.__name__ == "documented_async"
        assert documented_async.__doc__ == "Async docstring."

    def test_async_node9_skip_bypasses(self, monkeypatch):
        monkeypatch.setenv("NODE9_SKIP", "1")

        @protect("skipped_async")
        async def skipped(val: int) -> int:
            return val * 2

        result = asyncio.run(skipped(21))
        assert result == 42
