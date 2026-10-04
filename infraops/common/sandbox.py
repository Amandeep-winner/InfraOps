"""Safety guardrails restricting file access and process management to the sandbox."""

import os
from pathlib import Path

import psutil

from infraops.common.config import get_settings


class SandboxViolation(Exception):
    """Raised when an operation attempts to escape the designated sandbox boundaries."""


def get_sandbox_dir() -> Path:
    """Return the absolute, resolved path to the designated sandbox root directory."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox


def assert_in_sandbox(path: str | Path, allow_nonexistent: bool = True) -> Path:
    """Validate that a target path resides strictly inside the sandbox directory.

    Resolves symlinks, normalizes parent traversal ('..'), and prevents directory escapes.
    """
    sandbox_root = get_sandbox_dir()
    str_path = str(path).strip()
    if str_path.startswith("./sandbox") or str_path.startswith(".\\sandbox"):
        rel = str_path[9:].lstrip("/\\")
        target = sandbox_root / rel
    elif str_path.startswith("sandbox/") or str_path.startswith("sandbox\\"):
        rel = str_path[8:].lstrip("/\\")
        target = sandbox_root / rel
    elif str_path in ("./sandbox", ".\\sandbox", "sandbox"):
        target = sandbox_root
    else:
        target = Path(path)

    # If the path is relative, resolve it relative to current working directory or sandbox
    resolved_target = target.resolve()

    # Verify that the resolved target path has sandbox_root as its prefix/parent
    try:
        resolved_target.relative_to(sandbox_root)
    except ValueError:
        raise SandboxViolation(
            f"Access denied: path '{path}' (resolved: '{resolved_target}') "
            f"escapes sandbox boundary '{sandbox_root}'"
        )

    if not allow_nonexistent and not resolved_target.exists():
        raise FileNotFoundError(f"Sandbox file does not exist: {resolved_target}")

    return resolved_target


def is_sandbox_process(pid: int) -> bool:
    """Check whether a process carries the INFRAOPS_SIM=1 marker or --infraops-sim argument."""
    if pid <= 1:
        return False

    current_pid = os.getpid()
    if pid == current_pid:
        return False

    try:
        parent_pid = os.getppid()
        if pid == parent_pid:
            return False
    except AttributeError:
        pass

    # Fast check: verify if PID matches any known pidfile in sandbox/run
    try:
        run_dir = get_sandbox_dir() / "run"
        if run_dir.is_dir():
            for pf in run_dir.glob("*.pid"):
                try:
                    text = pf.read_text(encoding="utf-8").strip()
                    for part in text.split(","):
                        if part.strip().isdigit() and int(part.strip()) == pid:
                            return True
                except Exception:
                    pass
    except Exception:
        pass

    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

    # Check command-line arguments for marker
    try:
        cmdline = proc.cmdline()
        if any("--infraops-sim" in arg for arg in cmdline):
            return True
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    # Check environment variables for marker
    try:
        env = proc.environ()
        if env.get("INFRAOPS_SIM") == "1":
            return True
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass

    return False


def assert_sandbox_process(pid: int) -> psutil.Process:
    """Assert that the specified PID belongs to a safe, sandbox-marked simulation process."""
    if pid <= 1:
        raise SandboxViolation(f"Refusing to touch system root process PID {pid}")

    if pid == os.getpid():
        raise SandboxViolation("Refusing to target self process")

    try:
        if pid == os.getppid():
            raise SandboxViolation("Refusing to target parent process")
    except AttributeError:
        pass

    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        raise SandboxViolation(f"Process PID {pid} does not exist")
    except psutil.AccessDenied:
        raise SandboxViolation(f"Access denied to inspect PID {pid}")

    if not is_sandbox_process(pid):
        raise SandboxViolation(
            f"Process PID {pid} ('{proc.name()}') does not carry the sandbox marker "
            f"(INFRAOPS_SIM=1 or --infraops-sim). Remediation aborted."
        )

    return proc
