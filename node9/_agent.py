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

        _ALLOWED_SUITES = {"pytest", "pytest --tb=short", "ruff check ."}

        @tool("run_tests")
        def run_tests(self, suite: str) -> str:
            import shlex, subprocess
            # Always allowlist LLM-controlled commands — never pass raw strings to subprocess.
            if suite not in self._ALLOWED_SUITES:
                raise ValueError(f"Suite {suite!r} not in allowed list")
            return subprocess.check_output(shlex.split(suite), text=True)

        @tool("write_code")
        def write_code(self, filename: str, content: str) -> str:
            from node9 import safe_path
            path = safe_path(filename, workspace=self._workspace)  # workspace-relative, traversal-safe
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

import asyncio
import functools
import inspect
import os
import sys
import uuid
import warnings
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

    Note: DLP scanning only inspects top-level string arguments. Secrets nested
    inside dicts or lists will not be caught — flatten sensitive values or call
    dlp_scan() explicitly before passing structured data.
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

            # Path safety — check ALL string args that look like file paths.
            # We check every arg regardless of parameter name so that parameters
            # named dest, output, filepath, etc. are protected the same as filename.
            if hasattr(self, "_workspace") and self._workspace:
                for v in call_args.values():
                    if isinstance(v, str) and ("/" in v or "\\" in v):
                        try:
                            safe_path(v, workspace=self._workspace)
                        except ValueError as e:
                            raise ActionDeniedException(name, str(e)) from e

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
    - Logs to stderr: [node9 internal] method_name(args)
    - Use only for non-agent-decision code (git, workspace setup, file plumbing).
      Do NOT use to bypass governance on agent-controlled actions.
    - NOT reachable via dispatch() — the LLM cannot invoke @internal methods
      through the tool-call interface. dispatch() only routes to @tool methods.

    WARNING: @internal skips all governance. By convention, @internal methods
    should have names starting with '_' to make the bypass visible at call sites.
    A RuntimeWarning is raised if a public method name is decorated with @internal.
    """
    if not fn.__name__.startswith("_"):
        warnings.warn(
            f"@internal applied to public method '{fn.__name__}' — @internal skips all "
            "governance checks. Rename to '_{fn.__name__}' or use @tool instead.",
            RuntimeWarning,
            stacklevel=2,
        )

    @functools.wraps(fn)
    def wrapper(self: "Node9Agent", *args: Any, **kwargs: Any) -> Any:
        sig = inspect.signature(fn)
        bound = sig.bind(self, *args, **kwargs)
        bound.apply_defaults()
        call_args = {k: v for k, v in bound.arguments.items() if k != "self"}
        arg_summary = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in call_args.items())
        # Write to stderr, not stdout — LLM frameworks parse stdout for tool results
        # and a print() mid-execution would corrupt the JSON/text output stream.
        print(f"  [node9 internal] {fn.__name__}({arg_summary})", file=sys.stderr, flush=True)
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

        Thread safety: do NOT share a single Node9Agent instance across concurrent
        requests. _run_id assignment is not atomic. Use one instance per request
        (or per thread) to avoid run_id races in concurrent web servers.
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
        _config.set_identity(
            agent_name=self.agent_name or type(self).__name__,
            policy=self.policy,
        )

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
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
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

        Lookup is strictly registry-based: only methods decorated with @tool are
        reachable. Undecorated methods and arbitrary attribute names are never called.
        """
        # Lookup is strictly against the @tool decorator registry (_TOOL_ATTR marker).
        # Only methods explicitly decorated with @tool are callable via dispatch().
        for attr_name in dir(type(self)):
            method = getattr(type(self), attr_name, None)
            if method is None:
                continue
            if getattr(method, _TOOL_ATTR, None) == tool_name:
                try:
                    result = getattr(self, attr_name)(**tool_input)
                    if inspect.iscoroutine(result):
                        try:
                            asyncio.get_running_loop()
                            # Already inside an async event loop — dispatch() cannot
                            # await here. The caller should await the method directly:
                            #   result = await agent.method(**tool_input)
                            result.close()  # prevent "coroutine was never awaited" warning
                            return (
                                f"Error: '{tool_name}' is async. "
                                "In an async context, call it directly with 'await'."
                            )
                        except RuntimeError:
                            # RuntimeError here means "no running event loop" —
                            # the only error get_running_loop() raises. Safe to run.
                            result = asyncio.run(result)
                    return str(result) if result is not None else ""
                except ActionDeniedException as e:
                    return e.negotiation
                except Exception as e:
                    return f"Error: {e}"
        available = sorted(
            getattr(m, _TOOL_ATTR)
            for attr in dir(type(self))
            if (m := getattr(type(self), attr, None)) is not None
            and getattr(m, _TOOL_ATTR, None) is not None
        )
        return f"Unknown tool: {tool_name!r}. Available tools: {available}"

    def _dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Deprecated alias for dispatch(). Use dispatch() instead."""
        warnings.warn(
            "Node9Agent._dispatch() is deprecated — use .dispatch() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.dispatch(tool_name, tool_input)
