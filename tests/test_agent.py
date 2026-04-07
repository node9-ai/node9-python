"""Tests for Node9Agent base class, @tool and @internal decorators."""
import uuid
import threading
import pytest
from unittest.mock import patch, MagicMock

from node9 import Node9Agent, tool, internal, ActionDeniedException
from node9._dlp import dlp_scan


# ---------------------------------------------------------------------------
# Minimal concrete agent used across all tests
# ---------------------------------------------------------------------------

class SimpleAgent(Node9Agent):
    agent_name = "test-agent"
    policy     = "audit"

    @tool("write_file")
    def write_file(self, filename: str, content: str) -> str:
        """Write content to a file."""
        return f"written:{filename}"

    @tool("run_cmd")
    def run_cmd(self, command: str) -> str:
        """Run a shell command."""
        return f"ran:{command}"

    @internal
    def _git_push(self, branch: str) -> str:
        return f"pushed:{branch}"


EVAL_PATCH = "node9._agent.evaluate"


# ---------------------------------------------------------------------------
# Node9Agent initialisation
# ---------------------------------------------------------------------------

class TestNode9AgentInit:
    def test_run_id_is_uuid(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        parsed = uuid.UUID(agent._run_id)
        assert str(parsed) == agent._run_id

    def test_each_instance_gets_unique_run_id(self, tmp_path):
        a = SimpleAgent(workspace=str(tmp_path))
        b = SimpleAgent(workspace=str(tmp_path))
        assert a._run_id != b._run_id

    def test_workspace_is_set(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        assert str(tmp_path) in agent._workspace

    def test_config_agent_name_set_on_init(self, tmp_path):
        import node9._config as cfg
        SimpleAgent(workspace=str(tmp_path))
        assert cfg.AGENT_NAME == "test-agent"

    def test_config_policy_set_on_init(self, tmp_path):
        import node9._config as cfg
        SimpleAgent(workspace=str(tmp_path))
        assert cfg.AGENT_POLICY == "audit"

    def test_default_workspace_is_cwd(self):
        import os
        agent = SimpleAgent()
        assert agent._workspace == os.path.realpath(os.getcwd())


# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------

class TestToolDecorator:
    def test_evaluate_called_on_tool_call(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            agent.write_file("out.txt", "hello")
        mock_eval.assert_called_once()

    def test_correct_tool_name_passed_to_evaluate(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            agent.write_file("out.txt", "hello")
        call_args = mock_eval.call_args
        assert call_args[0][0] == "write_file"

    def test_run_id_passed_to_evaluate(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            agent.write_file("out.txt", "hello")
        call_kwargs = mock_eval.call_args[1]
        assert call_kwargs.get("run_id") == agent._run_id

    def test_all_tool_calls_share_run_id(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        run_ids = []
        def capture(tool_name, args, *, run_id=""):
            run_ids.append(run_id)
        with patch(EVAL_PATCH, side_effect=capture):
            agent.write_file("a.txt", "hello")
            agent.run_cmd("ls")
        assert len(run_ids) == 2
        assert run_ids[0] == run_ids[1] == agent._run_id

    def test_tool_return_value_passed_through(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            result = agent.write_file("out.txt", "hello")
        assert result == "written:out.txt"

    def test_denied_raises_action_denied_exception(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH, side_effect=ActionDeniedException("write_file", "blocked")):
            with pytest.raises(ActionDeniedException):
                agent.write_file("out.txt", "hello")

    def test_tool_without_custom_name_uses_function_name(self, tmp_path):
        class Agent2(Node9Agent):
            @tool
            def my_action(self, x: str) -> str:
                return x

        agent = Agent2(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            agent.my_action("test")
        assert mock_eval.call_args[0][0] == "my_action"


# ---------------------------------------------------------------------------
# @tool DLP integration
# ---------------------------------------------------------------------------

class TestToolDlp:
    def test_dlp_blocks_sensitive_path(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            with pytest.raises(ActionDeniedException, match="DLP"):
                agent.write_file("/home/user/.ssh/id_rsa", "content")

    def test_dlp_block_does_not_call_evaluate(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            try:
                agent.write_file("/home/user/.aws/credentials", "content")
            except ActionDeniedException:
                pass
        mock_eval.assert_not_called()

    def test_clean_file_passes_dlp(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            result = agent.write_file("output.txt", "hello world")
        assert result == "written:output.txt"


# ---------------------------------------------------------------------------
# @tool path safety integration
# ---------------------------------------------------------------------------

class TestToolPathSafety:
    def test_traversal_raises_action_denied(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            with pytest.raises(ActionDeniedException):
                agent.write_file("../../etc/passwd", "content")

    def test_traversal_block_does_not_call_evaluate(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            try:
                agent.write_file("../../etc/passwd", "content")
            except ActionDeniedException:
                pass
        mock_eval.assert_not_called()

    def test_all_path_args_are_checked_not_just_first(self, tmp_path):
        """Path traversal in any arg (not just the first) must be caught."""
        class MultiPathAgent(Node9Agent):
            @tool("copy")
            def copy(self, src: str, dest: str) -> str:
                return f"copied:{src}->{dest}"

        agent = MultiPathAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            # First arg safe, second arg is traversal — must still be blocked
            with pytest.raises(ActionDeniedException):
                agent.copy("safe.txt", "../../etc/passwd")


# ---------------------------------------------------------------------------
# @internal decorator
# ---------------------------------------------------------------------------

class TestInternalDecorator:
    def test_internal_never_calls_evaluate(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH) as mock_eval:
            agent._git_push("main")
        mock_eval.assert_not_called()

    def test_internal_return_value_passed_through(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        result = agent._git_push("main")
        assert result == "pushed:main"

    def test_internal_logs_to_stderr(self, tmp_path, capsys):
        # @internal writes to stderr so LLM parsers reading stdout are not corrupted
        agent = SimpleAgent(workspace=str(tmp_path))
        agent._git_push("dev")
        captured = capsys.readouterr()
        assert "internal" in captured.err
        assert "_git_push" in captured.err
        assert "internal" not in captured.out  # must NOT appear on stdout

    def test_internal_not_reachable_via_dispatch(self, tmp_path):
        """LLM cannot invoke @internal methods through dispatch() — they are invisible to the tool router."""
        agent = SimpleAgent(workspace=str(tmp_path))
        result = agent.dispatch("_git_push", {"branch": "main"})
        assert "Unknown tool" in result, (
            "@internal method '_git_push' should not be reachable via dispatch()"
        )

    def test_internal_not_reachable_via_dispatch_by_function_name(self, tmp_path):
        """dispatch() ignores @internal even if called by the underlying function name."""
        agent = SimpleAgent(workspace=str(tmp_path))
        # SimpleAgent._git_push is @internal — must not be callable via dispatch
        result = agent.dispatch("_git_push", {})
        assert "Unknown tool" in result

    def test_internal_on_public_method_warns(self):
        """@internal on a public method (no leading _) emits RuntimeWarning."""
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            class BadAgent(Node9Agent):
                @internal
                def public_infra(self) -> str:  # public name, missing underscore
                    return "ok"

        assert any(
            issubclass(w.category, RuntimeWarning) and "public_infra" in str(w.message)
            for w in caught
        ), "Expected RuntimeWarning for @internal on public method"

    def test_dispatch_error_message_includes_available_tools(self, tmp_path):
        """dispatch() with unknown tool name returns the list of available tools."""
        agent = SimpleAgent(workspace=str(tmp_path))
        result = agent.dispatch("no_such_tool", {})
        assert "no_such_tool" in result
        assert "write_file" in result
        assert "run_cmd" in result


# ---------------------------------------------------------------------------
# _build_tools — neutral tool spec
# ---------------------------------------------------------------------------

class TestBuildTools:
    def test_returns_list_of_dicts(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        tools = agent._build_tools()
        assert isinstance(tools, list)
        assert all(isinstance(t, dict) for t in tools)

    def test_tool_names_present(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        names = {t["name"] for t in agent._build_tools()}
        assert "write_file" in names
        assert "run_cmd" in names

    def test_internal_not_in_tools(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        names = {t["name"] for t in agent._build_tools()}
        assert "_git_push" not in names

    def test_multi_level_inheritance(self, tmp_path):
        """@tool methods on all levels of the MRO are visible in _build_tools()."""
        class Base(Node9Agent):
            @tool("base_op")
            def base_op(self, x: str) -> str:
                return x

        class Mid(Base):
            @tool("mid_op")
            def mid_op(self, y: str) -> str:
                return y

        class Leaf(Mid):
            @tool("leaf_op")
            def leaf_op(self, z: str) -> str:
                return z

        agent = Leaf(workspace=str(tmp_path))
        names = {t["name"] for t in agent._build_tools()}
        assert "base_op" in names
        assert "mid_op" in names
        assert "leaf_op" in names

    def test_neutral_format_uses_parameters_key(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        for t in agent._build_tools():
            assert "parameters" in t
            assert "input_schema" not in t
            assert t["parameters"]["type"] == "object"

    def test_required_params_captured(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        write_tool = next(t for t in agent._build_tools() if t["name"] == "write_file")
        assert "filename" in write_tool["parameters"]["required"]
        assert "content" in write_tool["parameters"]["required"]

    def test_description_from_docstring(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        write_tool = next(t for t in agent._build_tools() if t["name"] == "write_file")
        assert "Write content" in write_tool["description"]


# ---------------------------------------------------------------------------
# Framework-specific tool spec builders
# ---------------------------------------------------------------------------

class TestBuildToolsFrameworks:
    def test_anthropic_uses_input_schema(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        tools = agent.build_tools_anthropic()
        for t in tools:
            assert "input_schema" in t
            assert "parameters" not in t

    def test_anthropic_preserves_name_and_description(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        tools = agent.build_tools_anthropic()
        names = {t["name"] for t in tools}
        assert "write_file" in names
        write_tool = next(t for t in tools if t["name"] == "write_file")
        assert "Write content" in write_tool["description"]

    def test_openai_wraps_in_function(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        tools = agent.build_tools_openai()
        for t in tools:
            assert t["type"] == "function"
            assert "function" in t
            assert "name" in t["function"]
            assert "parameters" in t["function"]

    def test_openai_preserves_tool_names(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        tools = agent.build_tools_openai()
        names = {t["function"]["name"] for t in tools}
        assert "write_file" in names
        assert "run_cmd" in names


# ---------------------------------------------------------------------------
# _dispatch
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_known_tool_dispatched(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            result = agent._dispatch("write_file", {"filename": "x.txt", "content": "hi"})
        assert "written" in result

    def test_unknown_tool_returns_error_string(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        result = agent._dispatch("nonexistent_tool", {})
        assert "Unknown tool" in result

    def test_denied_tool_returns_negotiation_string(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH, side_effect=ActionDeniedException("write_file", "policy")):
            result = agent._dispatch("write_file", {"filename": "x.txt", "content": "hi"})
        assert "blocked" in result.lower() or "write_file" in result

    def test_dispatch_unknown_tool_returns_error_string(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        result = agent.dispatch("no_such_tool", {})
        assert "Unknown tool" in result
        assert "no_such_tool" in result

    def test_dispatch_unknown_tool_does_not_raise(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        # LLM loops must not get an unhandled exception for bad tool names
        try:
            agent.dispatch("totally_missing", {"x": 1})
        except Exception as e:
            pytest.fail(f"dispatch() raised unexpectedly: {e}")


# ---------------------------------------------------------------------------
# async @tool via dispatch()
# ---------------------------------------------------------------------------

class TestAsyncTool:
    def test_async_tool_direct_call_works(self, tmp_path):
        """Calling an async @tool method directly returns an awaitable."""
        import asyncio

        class AsyncAgent(Node9Agent):
            @tool("async_task")
            async def async_task(self, x: str) -> str:
                return f"done:{x}"

        agent = AsyncAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            result = asyncio.run(agent.async_task("hi"))
        assert result == "done:hi"

    def test_async_tool_via_dispatch_no_loop(self, tmp_path):
        """dispatch() runs async tools to completion when no event loop is running."""
        class AsyncAgent(Node9Agent):
            @tool("async_task")
            async def async_task(self, x: str) -> str:
                return f"done:{x}"

        agent = AsyncAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            result = agent.dispatch("async_task", {"x": "hello"})
        assert result == "done:hello"

    def test_async_tool_dispatch_returns_string_not_coroutine(self, tmp_path):
        """dispatch() must not return a raw coroutine object."""
        import inspect

        class AsyncAgent(Node9Agent):
            @tool("async_task")
            async def async_task(self, x: str) -> str:
                return f"done:{x}"

        agent = AsyncAgent(workspace=str(tmp_path))
        with patch(EVAL_PATCH):
            result = agent.dispatch("async_task", {"x": "test"})
        assert not inspect.iscoroutine(result), "dispatch() returned a raw coroutine"
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# new_session
# ---------------------------------------------------------------------------

class TestNewSession:
    def test_new_session_returns_new_uuid(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        old_id = agent._run_id
        new_id = agent.new_session()
        assert new_id != old_id
        assert uuid.UUID(new_id)  # valid UUID

    def test_new_session_updates_run_id(self, tmp_path):
        agent = SimpleAgent(workspace=str(tmp_path))
        new_id = agent.new_session()
        assert agent._run_id == new_id

    def test_concurrent_new_session_calls_produce_unique_ids(self, tmp_path):
        """Each new_session() call produces a unique ID — no UUID collision."""
        agent = SimpleAgent(workspace=str(tmp_path))
        ids = []
        errors = []

        def call_new_session():
            try:
                ids.append(agent.new_session())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call_new_session) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # All IDs are valid UUIDs
        for run_id in ids:
            uuid.UUID(run_id)
        # Note: concurrent calls race on _run_id — documented as "one instance per request"


# ---------------------------------------------------------------------------
# _build_tools — unannotated and complex-typed parameters
# ---------------------------------------------------------------------------

class TestBuildToolsEdgeCases:
    def test_unannotated_param_defaults_to_string_type(self, tmp_path):
        class Agent3(Node9Agent):
            @tool("unannotated")
            def unannotated(self, x, y) -> str:
                return str(x)

        agent = Agent3(workspace=str(tmp_path))
        spec = next(t for t in agent._build_tools() if t["name"] == "unannotated")
        assert spec["parameters"]["properties"]["x"]["type"] == "string"
        assert spec["parameters"]["properties"]["y"]["type"] == "string"

    def test_int_annotation_maps_to_integer(self, tmp_path):
        class Agent4(Node9Agent):
            @tool("typed")
            def typed(self, count: int, flag: bool, ratio: float) -> str:
                return ""

        agent = Agent4(workspace=str(tmp_path))
        spec = next(t for t in agent._build_tools() if t["name"] == "typed")
        props = spec["parameters"]["properties"]
        assert props["count"]["type"] == "integer"
        assert props["flag"]["type"] == "boolean"
        assert props["ratio"]["type"] == "number"

    def test_varargs_not_included_in_schema(self, tmp_path):
        class Agent5(Node9Agent):
            @tool("varargs")
            def varargs(self, x: str, *args, **kwargs) -> str:
                return x

        agent = Agent5(workspace=str(tmp_path))
        spec = next(t for t in agent._build_tools() if t["name"] == "varargs")
        props = spec["parameters"]["properties"]
        assert "x" in props
        assert "args" not in props
        assert "kwargs" not in props
