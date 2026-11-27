from windows_mcp.infrastructure.thread_affinity import run_uia_affine
from typing import TypeVar, Callable, Awaitable
from functools import wraps
import inspect
import asyncio
import logging
import time


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

T = TypeVar("T")


def run_tool(*, run_sync_in_thread: bool = True):
    """
    Decorator that dispatches a tool function and logs its outcome locally.

    Args:
        run_sync_in_thread: For a synchronous ``func``, dispatch the call to a generic
            worker thread so it cannot block the event loop (the default). Set to False
            for UIAutomation/comtypes-affine tools: they run on the single dedicated UIA
            worker instead, preserving COM apartment affinity without blocking the MCP
            event loop. Ignored for async ``func``; async tools that need UIA must call
            ``run_uia_affine`` around the UIA operation itself.
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            start = time.time()

            try:
                if inspect.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                elif run_sync_in_thread:
                    # Generic synchronous work stays off the MCP event loop.
                    result = await asyncio.to_thread(func, *args, **kwargs)
                else:
                    # UIA-affine synchronous work is serialized on one dedicated
                    # apartment thread, so WaitFor and slow providers cannot freeze
                    # cancellation, pings, or unrelated MCP tool calls.
                    result = await run_uia_affine(func, *args, **kwargs)

                duration_ms = int((time.time() - start) * 1000)
                logger.info(f"{func.__name__}: SUCCESS ({duration_ms}ms)")
                return result
            except Exception as error:
                duration_ms = int((time.time() - start) * 1000)
                logger.error(f"ERROR in {func.__name__} after {duration_ms}ms: {error}")
                raise error

        return wrapper

    return decorator
