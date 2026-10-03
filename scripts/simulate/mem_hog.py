"""Memory hog simulator: safely consumes RAM up to a strict cap with sandbox marker."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psutil

from infraops.common.config import get_settings


def start_mem_hog(cap_mb: int = 150):
    """Launch a background worker process that allocates memory up to cap_mb."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    run_dir = sandbox / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    pidfile = run_dir / "mem_hog.pid"

    stop_mem_hog()

    worker_code = (
        "import os, time, sys\n"
        "os.environ['INFRAOPS_SIM'] = '1'\n"
        f"cap_mb = {cap_mb}\n"
        "chunks = [b'M' * (1024 * 1024) for _ in range(cap_mb)]\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )

    env = os.environ.copy()
    env["INFRAOPS_SIM"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-c", worker_code, "--infraops-sim"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pidfile.write_text(str(proc.pid), encoding="utf-8")
    sys.stderr.write(f"[simulate.mem_hog] Started memory worker PID {proc.pid} (cap: {cap_mb}MB)\n")
    return proc.pid


def stop_mem_hog():
    """Stop the running memory hog worker process."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    pidfile = sandbox / "run" / "mem_hog.pid"
    if not pidfile.is_file():
        return

    try:
        content = pidfile.read_text(encoding="utf-8").strip()
        if content:
            pid = int(content)
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=1.0)
                except psutil.TimeoutExpired:
                    p.kill()
    except Exception:
        pass
    finally:
        pidfile.unlink(missing_ok=True)
        sys.stderr.write("[simulate.mem_hog] Stopped memory hog worker.\n")


def main():
    parser = argparse.ArgumentParser(description="Memory Hog Simulator")
    parser.add_argument("--stop", action="store_true", help="Stop running memory hog worker")
    parser.add_argument("--cap-mb", type=int, default=150, help="Target MB to allocate")
    parser.add_argument("--infraops-sim", action="store_true", help="Simulation marker")
    args = parser.parse_args()

    if args.stop:
        stop_mem_hog()
    else:
        start_mem_hog(cap_mb=args.cap_mb)


if __name__ == "__main__":
    main()
