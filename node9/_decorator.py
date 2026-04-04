import asyncio
import functools
import inspect
from typing import Any, Callable, Optional

from ._client import evaluate


def _capture_args(func: Callable, params: Optional[Callable], *args: Any, **kwargs: Any) -> dict:
    if params is not None:
        return params(*args, **kwargs)
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()
    return dict(bound.arguments)


def protect(
    tool_name: Optional[str] = None,
    *,
    params: Optional[Callable[..., dict]] = None,
):
    """
    Decorator that intercepts a function call and asks Node9 for approval.

    Works with both sync and async functions.

    Usage:
        @protect("write_file")
        def write_file(path: str, content: str): ...

        @protect("bash", params=lambda cmd, **_: {"command": cmd})
        async def run_shell(cmd: str): ...

    If no `params` lambda is provided, all arguments are captured automatically
    using inspect.signature — no configuration needed.
    """

    def decorator(func: Callable) -> Callable:
        name = tool_name or func.__name__

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                captured = _capture_args(func, params, *args, **kwargs)
                # Run blocking HTTP call in a thread to avoid blocking the event loop
                await asyncio.to_thread(evaluate, name, captured)
                return await func(*args, **kwargs)
            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            captured = _capture_args(func, params, *args, **kwargs)
            evaluate(name, captured)
            return func(*args, **kwargs)

        return wrapper

    # Support both @protect and @protect("name") usage
    if callable(tool_name):
        func = tool_name
        tool_name = func.__name__
        return decorator(func)

    return decorator
