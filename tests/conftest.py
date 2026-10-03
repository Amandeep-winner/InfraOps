"""Pytest configuration and global test fixtures."""

import asyncio
import os
import shutil
import tempfile
import time
from typing import Any, Awaitable, Callable, Union

import pytest


def wait_until(
    predicate: Callable[[], Union[bool, Any]],
    timeout: float = 10.0,
    interval: float = 0.1,
    description: str = "condition",
) -> Any:
    """Poll a predicate synchronously until it returns a truthy value or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    raise TimeoutError(f"Timed out after {timeout}s waiting for {description}")


async def async_wait_until(
    predicate: Callable[[], Union[Awaitable[Any], Any]],
    timeout: float = 10.0,
    interval: float = 0.1,
    description: str = "async condition",
) -> Any:
    """Poll an async or sync predicate until truthy or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = predicate()
        if asyncio.iscoroutine(res):
            res = await res
        if res:
            return res
        await asyncio.sleep(interval)
    raise TimeoutError(f"Timed out after {timeout}s waiting for {description}")


@pytest.fixture
def temp_sandbox():
    """Create a temporary sandbox directory for test isolation."""
    sandbox_dir = tempfile.mkdtemp(prefix="infraops_test_sandbox_")
    subdirs = ["data", "logs", "run", "faults", "spool"]
    for sub in subdirs:
        os.makedirs(os.path.join(sandbox_dir, sub), exist_ok=True)
    old_env = os.environ.get("INFRAOPS_SANDBOX_DIR")
    os.environ["INFRAOPS_SANDBOX_DIR"] = sandbox_dir
    yield sandbox_dir
    if old_env is not None:
        os.environ["INFRAOPS_SANDBOX_DIR"] = old_env
    else:
        os.environ.pop("INFRAOPS_SANDBOX_DIR", None)
    shutil.rmtree(sandbox_dir, ignore_errors=True)
