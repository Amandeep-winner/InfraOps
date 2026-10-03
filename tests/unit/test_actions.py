"""Unit tests for allowlisted SOP actions and security guardrails."""

import os
import subprocess
import sys

import pytest

from infraops.common.config import reset_settings
from infraops.common.sandbox import SandboxViolation, get_sandbox_dir
from infraops.server.sop.actions import (
    ALLOWLISTED_ACTIONS,
    execute_action,
)


def test_allowlist_completeness():
    """Verify core allowlisted actions exist in registry."""
    required = {
        "collect_snapshot",
        "top_processes",
        "identify_offender",
        "renice_process",
        "kill_process",
        "memory_report",
        "disk_report",
        "find_large_files",
        "clean_path",
        "service_status",
        "service_start",
        "service_restart",
        "check_logs",
        "dns_diagnose",
        "dns_switch_resolver",
        "ping_check",
        "tcp_check",
        "restart_dependency",
        "notify",
    }
    for action in required:
        assert action in ALLOWLISTED_ACTIONS


def test_reject_arbitrary_actions():
    """Verify non-allowlisted action names raise ValueError."""
    with pytest.raises(ValueError):
        execute_action("arbitrary_bash_shell", {"cmd": "rm -rf /"})

    with pytest.raises(ValueError):
        execute_action("format_hard_drive", {})


def test_kill_process_guardrails():
    """Verify kill_process cannot touch root PID 1, self, or unmarked processes."""
    with pytest.raises(SandboxViolation):
        execute_action("kill_process", {"pid": 0})

    with pytest.raises(SandboxViolation):
        execute_action("kill_process", {"pid": 1})

    with pytest.raises(SandboxViolation):
        execute_action("kill_process", {"pid": os.getpid()})

    # Unmarked process
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        with pytest.raises(SandboxViolation):
            execute_action("kill_process", {"pid": proc.pid})
    finally:
        proc.kill()
        proc.wait()


def test_kill_process_accepts_sandbox_marked():
    """Verify kill_process successfully terminates sandbox-marked process."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)", "--infraops-sim"])
    try:
        res = execute_action("kill_process", {"pid": proc.pid, "grace_seconds": 1})
        assert "Terminated" in res or "Killed" in res or "exited" in res
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def test_file_clean_path_guardrails(temp_sandbox):
    """Verify clean_path and find_large_files cannot escape sandbox."""
    reset_settings()
    sandbox = get_sandbox_dir()

    # Create safe files inside sandbox
    data_dir = sandbox / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    f1 = data_dir / "test1.log"
    f1.write_text("junk data" * 100)

    # find_large_files inside sandbox
    found = execute_action("find_large_files", {"path": str(data_dir)})
    assert len(found) >= 1

    # clean_path inside sandbox
    res = execute_action("clean_path", {"path": str(data_dir), "pattern": "*.log"})
    assert res["files_deleted"] >= 1
    assert not f1.exists()

    # Attempt path escape
    with pytest.raises(SandboxViolation):
        execute_action("clean_path", {"path": str(sandbox / ".." / "system_dir")})


def test_dns_switch_resolver_guardrail(temp_sandbox):
    """Verify dns_switch_resolver validates that the flag is inside the sandbox."""
    reset_settings()
    sandbox = get_sandbox_dir()

    faults_dir = sandbox / "faults"
    faults_dir.mkdir(parents=True, exist_ok=True)
    flag = faults_dir / "dns_fail"
    flag.write_text("1")

    res = execute_action("dns_switch_resolver", {"remove_flag": str(flag)})
    assert "Removed DNS fault flag" in res
    assert not flag.exists()

    # Attempt escape
    with pytest.raises(SandboxViolation):
        execute_action(
            "dns_switch_resolver", {"remove_flag": str(sandbox / ".." / "etc" / "resolv.conf")}
        )
