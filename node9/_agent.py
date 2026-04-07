"""
Node9Agent — governance base class for AI agents.

Provides @tool and @internal decorators plus the Node9Agent base class.
Does NOT include an LLM loop — that is the framework's responsibility.

The LLM loop lives in the agent that subclasses Node9Agent. This keeps the
SDK framework-agnostic and dependency-free (zero imports beyond stdlib).

Usage:
    from node9 import Node9Agent, tool, internal

    class CiAgent(Node9Agent):
        agent_name = "ci-code-review"
        policy     = "audit"

        @tool("run_tests")
        def run_tests(self, command: str) -> str:
            import shlex, subprocess
            # Use shell=False to avoid injection — split the command string safely
            return subprocess.check_output(shlex.split(command), text=True)

        @tool("write_code")
        def write_code(self, filename: str, content: str) -> str:
            from node9 import safe_path
            path = safe_path(filename, self._workspace)  # workspace-relative, traversal-safe
            with open(path, "w") as f:
                f.write(content)
            return f"written:{filename}"

        @internal
        def _git_push(self, branch: str) -> str:
            # never calls evaluate() — infrastructure only
            import subprocess
            subprocess.run(["git", "push", "origin", branch], check=True)
            return f"pushed:{branch}"

    agent = CiAgent(workspace="/path/to/repo")

    # The LLM loop is YOUR code — use whichever framework you want:
    #   Anthropic: tools = agent.build_tools_anthropic()
    #   OpenAI:    tools = agent.build_tools_openai()
    #   Custom:    tools = agent._build_tools()  # neutral format
    #
    # Dispatch tool calls from the LLM response:
    #   result = agent.dispatch(tool_name, tool_input)
"""

import functools
import inspect
import os
import uuid
from typing import Any, Callable, Union

from ._client import evaluate
from ._dlp import dlp_scan, safe_path
from ._exceptions import ActionDeniedException

# Marker attributes written by decorators so Node9Agent can introspect methods
_TOOL_ATTR     = "_node9_tool"
_INTERNAL_ATTR = "_node9_internal"


def tool(tool_name: Union[str, Callable]):
    """
    Marks a Node9Agent method as a governed tool.

    Before every call:
    - DLP scan  — blocks if filename/content contains a secret or sensitive path
    - Path safety — rejects ../traversal attempts
    - evaluate() — respects the agent's declared policy (audit / require_approval / etc.)
    - run_id    — injected automatically so all calls in one run are grouped in the dashboard

    Can be used as @tool or @tool("custom_name").
    """
    def decorator(fn: Callable, name: str) -> Callable:
        @functools.wraps(fn)
        def wrapper(self: "Node9Agent", *args: Any, **kwargs: Any) -> Any:
            sig = inspect.signature(fn)
            bound = sig.bind(self, *args, **kwargs)
            bound.apply_defaults()
            call_args = {k: v for k, v in bound.arguments.items() if k != "self"}

            # DLP scan — run once per string arg as both path and content candidate
            # This catches sensitive paths regardless of parameter name (e.g. dest, target)
            string_args = [str(v) for v in call_args.values() if isinstance(v, str)]
            all_content = "\n".join(string_args)
            for candidate in string_args:
                hit = dlp_scan(candidate, all_content)
                if hit:
                    raise ActionDeniedException(name, f"DLP blocked: {hit}")

            # Path safety — any arg that looks like a file path
            if hasattr(self, "_workspace") and self._workspace:
                for v in call_args.values():
                    if isinstance(v, str) and ("/" in v or "\\" in v):
                        try:
                            safe_path(v, self._workspace)
                        except ValueError as e:
                            raise ActionDeniedException(name, str(e)) from e
                        break

            run_id = getattr(self, "_run_id", "")
            evaluate(name, call_args, run_id=run_id)
            return fn(self, *args, **kwargs)

        setattr(wrapper, _TOOL_ATTR, name)
        return wrapper

    if callable(tool_name):
        fn = tool_name
        return decorator(fn, fn.__name__)

    def outer(fn: Callable) -> Callable:
        return decorator(fn, tool_name)

    return outer


def internal(fn: Callable) -> Callable:
    """
    Marks a Node9Agent method as infrastructure (git plumbing, workspace setup).

    - Never calls evaluate() — no SaaS call, no blocking, no DLP scan
    - Logs to stdout: [node9 internal] method_name(args)
    - Use only for non-agent-decision code (git, workspace setup, file plumbing).
      Do NOT use to bypass governance on agent-controlled actions.
    """
    @functools.wraps(fn)
    def wrapper(self: "Node9Agent", *args: Any, **kwargs: Any) -> Any:
        sig = inspect.signature(fn)
        bound = sig.bind(self, *args, **kwargs)
        bound.apply_defaults()
        call_args = {k: v for k, v in bound.arguments.items() if k != "self"}
        arg_summary = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in call_args.items())
        print(f"  [node9 internal] {fn.__name__}({arg_summary})", flush=True)
        return fn(self, *args, **kwargs)

    setattr(wrapper, _INTERNAL_ATTR, True)
    return wrapper


class Node9Agent:
    """
    Governance base class for AI agents. Framework-agnostic, zero dependencies.

    Provides:
    - Agent identity and policy (set once, applied to every tool call)
    - Per-run UUID for grouping audit entries in the dashboard
    - build_tools_anthropic() — Anthropic input_schema format
    - build_tools_openai()    — OpenAI parameters format
    - dispatch()      — route LLM tool calls to @tool methods (primary integration point)

    The LLM loop is NOT here — implement it in your subclass using whichever
    framework or API client you need.

    When to use Node9Agent vs @protect:
    - Node9Agent: greenfield agents where you control the tool definitions
    - @protect:   retrofitting governance onto existing functions/classes
    """

    agent_name: str = ""
    policy:     str = "audit"

    def new_session(self) -> str:
        """
        Start a new session — generates a fresh run_id so audit entries are
        grouped correctly. Call at the start of each user request in server deployments.
        Returns the new run_id.
        """
        self._run_id = str(uuid.uuid4())
        return self._run_id

    def __init__(self, workspace: str = ""):
        self._run_id = str(uuid.uuid4())  # one run_id per instance; call new_session() per request
        if workspace:
            resolved = os.path.realpath(workspace)
            if not os.path.isdir(resolved):
                raise ValueError(
                    f"Node9Agent workspace does not exist: {workspace!r}. "
                    "Create the directory before constructing the agent."
                )
            self._workspace = resolved
        else:
            self._workspace = os.getcwd()

        from . import _config
        _config.AGENT_NAME   = self.agent_name or type(self).__name__
        _config.AGENT_POLICY = self.policy

    # -------------------------------------------------------------------------
    # Tool spec builders — pick the format your LLM expects
    # -------------------------------------------------------------------------

    def _build_tools(self) -> list[dict]:
        """
        Neutral tool spec list. Keys: name, description, parameters (JSON Schema).

        Convert for your LLM:
          Anthropic: rename 'parameters' → 'input_schema'
          OpenAI:    wrap in {"type": "function", "function": spec}
        """
        tools = []
        for attr_name in dir(type(self)):
            method = getattr(type(self), attr_name, None)
            if method is None:
                continue
            tool_name = getattr(method, _TOOL_ATTR, None)
            if tool_name is None:
                continue

            original = inspect.unwrap(method)
            sig = inspect.signature(original)
            description = (inspect.getdoc(original) or tool_name).split("\n")[0]

            properties: dict[str, Any] = {}
            required: list[str] = []

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                prop: dict[str, Any] = {"type": "string"}
                ann = param.annotation
                if ann is not inspect.Parameter.empty:
                    if ann is int:   prop["type"] = "integer"
                    elif ann is float: prop["type"] = "number"
                    elif ann is bool:  prop["type"] = "boolean"
                properties[param_name] = prop
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

            tools.append({
                "name": tool_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            })
        return tools

    def build_tools_anthropic(self) -> list[dict]:
        """Tool specs in Anthropic format (input_schema key)."""
        result = []
        for spec in self._build_tools():
            result.append({
                "name": spec["name"],
                "description": spec["description"],
                "input_schema": spec["parameters"],
            })
        return result

    def build_tools_openai(self) -> list[dict]:
        """Tool specs in OpenAI format (type=function wrapper)."""
        result = []
        for spec in self._build_tools():
            result.append({
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": spec["parameters"],
                },
            })
        return result

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        """
        Route a tool call by name to the matching @tool method.
        Returns a string result — or negotiation text if the action was denied.

        This is the primary integration point for LLM loops:
            result = agent.dispatch(block.name, block.input)  # Anthropic
            result = agent.dispatch(call.function.name, json.loads(call.function.arguments))  # OpenAI
        """
        for attr_name in dir(type(self)):
            method = getattr(type(self), attr_name, None)
            if method is None:
                continue
            if getattr(method, _TOOL_ATTR, None) == tool_name:
                try:
                    result = getattr(self, attr_name)(**tool_input)
                    return str(result) if result is not None else ""
                except ActionDeniedException as e:
                    return e.negotiation
                except Exception as e:
                    return f"Error: {e}"
        return f"Unknown tool: {tool_name}"

    def _dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Deprecated alias for dispatch(). Use dispatch() instead."""
        import warnings
        warnings.warn(
            "Node9Agent._dispatch() is deprecated — use .dispatch() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.dispatch(tool_name, tool_input)
