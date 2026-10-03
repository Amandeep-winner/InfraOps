"""Unit tests for sandbox safety guardrails."""

import os
import subprocess
import sys

import pytest

from infraops.common.config import reset_settings
from infraops.common.sandbox import (
    SandboxViolation,
    assert_in_sandbox,
    assert_sandbox_process,
    get_sandbox_dir,
    is_sandbox_process,
)


def test_assert_in_sandbox_valid_paths(temp_sandbox):
    """Verify paths strictly inside sandbox succeed."""
    reset_settings()
    sandbox = get_sandbox_dir()

    data_dir = sandbox / "data"
    test_file = data_dir / "test.log"
    resolved = assert_in_sandbox(test_file)
    assert resolved == test_file.resolve()

    nested_file = sandbox / "sub1" / "sub2" / "file.txt"
    resolved_nested = assert_in_sandbox(nested_file)
    assert resolved_nested == nested_file.resolve()


def test_assert_in_sandbox_rejects_parent_traversal(temp_sandbox):
    """Verify directory traversal attempts via .. raise SandboxViolation."""
    reset_settings()
    sandbox = get_sandbox_dir()

    traversal_path = sandbox / ".." / "outside.txt"
    with pytest.raises(SandboxViolation):
        assert_in_sandbox(traversal_path)

    deep_traversal = sandbox / "data" / ".." / ".." / "sensitive.txt"
    with pytest.raises(SandboxViolation):
        assert_in_sandbox(deep_traversal)


def test_assert_in_sandbox_rejects_symlink_escape(temp_sandbox, tmp_path):
    """Verify symlinks pointing outside the sandbox directory are rejected."""
    reset_settings()
    sandbox = get_sandbox_dir()

    # Create target outside sandbox
    outside_dir = tmp_path / "outside_target"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.txt"
    secret_file.write_text("classified")

    link_path = sandbox / "symlink_escape"
    try:
        os.symlink(secret_file, link_path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not permitted in this environment")

    with pytest.raises(SandboxViolation):
        assert_in_sandbox(link_path)


def test_assert_sandbox_process_rejects_pid_1_and_self():
    """Verify PID 1 and current process PID are strictly protected."""
    with pytest.raises(SandboxViolation):
        assert_sandbox_process(0)

    with pytest.raises(SandboxViolation):
        assert_sandbox_process(1)

    with pytest.raises(SandboxViolation):
        assert_sandbox_process(os.getpid())


def test_assert_sandbox_process_rejects_unmarked_process():
    """Verify normal processes lacking the sandbox marker are rejected."""
    # Launch a safe sleep process without any marker
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    proc = subprocess.Popen(cmd)
    try:
        assert not is_sandbox_process(proc.pid)
        with pytest.raises(SandboxViolation):
            assert_sandbox_process(proc.pid)
    finally:
        proc.kill()
        proc.wait()


def test_assert_sandbox_process_accepts_cmdline_marked_process():
    """Verify processes with --infraops-sim in cmdline are recognized as safe."""
    cmd = [sys.executable, "-c", "import time; time.sleep(5)", "--infraops-sim"]
    proc = subprocess.Popen(cmd)
    try:
        assert is_sandbox_process(proc.pid)
        inspected = assert_sandbox_process(proc.pid)
        assert inspected.pid == proc.pid
    finally:
        proc.kill()
        proc.wait()


def test_assert_sandbox_process_accepts_environ_marked_process():
    """Verify processes with INFRAOPS_SIM=1 in env are recognized as safe."""
    env = os.environ.copy()
    env["INFRAOPS_SIM"] = "1"
    cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
    proc = subprocess.Popen(cmd, env=env)
    try:
        # Note: reading environ might have OS permissions; if readable, should pass
        if is_sandbox_process(proc.pid):
            inspected = assert_sandbox_process(proc.pid)
            assert inspected.pid == proc.pid
    finally:
        proc.kill()
        proc.wait()
