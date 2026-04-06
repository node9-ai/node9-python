"""Tests for Node9Agent base class, @tool and @internal decorators."""
import uuid
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

    def test_internal_logs_to_stdout(self, tmp_path, capsys):
        agent = SimpleAgent(workspace=str(tmp_path))
        agent._git_push("dev")
        captured = capsys.readouterr()
        assert "internal" in captured.out
        assert "_git_push" in captured.out


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
