"""Pidfile-based process supervisor for managed demo services."""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import psutil

from infraops.common.config import get_settings


class ServiceManager:
    """Supervises background service processes via pidfiles inside the sandbox."""

    SERVICE_MODULES = {
        "demo-service": "infraops.demo.demo_service",
        "demo-upstream": "infraops.demo.demo_upstream",
    }

    def __init__(self, service_name: str, sandbox_dir: Optional[str] = None) -> None:
        self.service_name = service_name
        settings = get_settings()
        root = Path(sandbox_dir or settings.sandbox_dir).resolve()
        self.run_dir = root / "run"
        self.log_dir = root / "logs"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.pidfile = self.run_dir / f"{service_name}.pid"
        self.logfile = self.log_dir / f"{service_name}.log"

    def get_pid(self) -> Optional[int]:
        """Read PID from pidfile if it exists."""
        if not self.pidfile.is_file():
            return None
        try:
            val = self.pidfile.read_text(encoding="utf-8").strip()
            return int(val)
        except Exception:
            return None

    def is_running(self) -> bool:
        """Check whether the supervised process is alive and active."""
        pid = self.get_pid()
        if not pid:
            return False
        if not psutil.pid_exists(pid):
            return False
        try:
            p = psutil.Process(pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def start(self) -> int:
        """Start the managed service as a detached background process."""
        if self.is_running():
            pid = self.get_pid()
            assert pid is not None
            return pid

        module = self.SERVICE_MODULES.get(self.service_name)
        if not module:
            raise ValueError(
                f"Unknown service '{self.service_name}'. Known: {list(self.SERVICE_MODULES.keys())}"
            )

        cmd = [sys.executable, "-m", module, "--infraops-sim"]
        env = os.environ.copy()
        env["INFRAOPS_SIM"] = "1"

        out_fd = self.logfile.open("a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=out_fd,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=(sys.platform != "win32"),
        )
        self.pidfile.write_text(str(proc.pid), encoding="utf-8")
        time.sleep(0.2)
        return proc.pid

    def stop(self, timeout: float = 3.0) -> bool:
        """Stop the service by sending SIGTERM, escalating to SIGKILL if necessary."""
        pid = self.get_pid()
        if not pid or not psutil.pid_exists(pid):
            self.pidfile.unlink(missing_ok=True)
            return True

        try:
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=timeout)
            except psutil.TimeoutExpired:
                p.kill()
                p.wait(timeout=1.0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        finally:
            self.pidfile.unlink(missing_ok=True)

        return True

    def restart(self) -> int:
        """Stop if running and start anew."""
        self.stop()
        time.sleep(0.2)
        return self.start()
