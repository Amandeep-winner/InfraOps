"""CPU hog simulator: spawns busy-loop workers carrying the sandbox simulation marker."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psutil

from infraops.common.config import get_settings


def _busy_worker():
    """Worker function consuming 100% of a CPU core."""
    while True:
        _ = 234234 * 987987


def start_cpu_hog(num_workers: int = 2):
    """Start CPU hog workers as background processes carrying the simulation marker."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    run_dir = sandbox / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    pidfile = run_dir / "cpu_hog.pid"

    # Stop any existing hog first
    stop_cpu_hog()

    worker_code = (
        "import os\nos.environ['INFRAOPS_SIM'] = '1'\nwhile True:\n    _ = 123456 * 654321\n"
    )

    env = os.environ.copy()
    env["INFRAOPS_SIM"] = "1"

    pids = []
    for _ in range(num_workers):
        proc = subprocess.Popen(
            [sys.executable, "-c", worker_code, "--infraops-sim"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pids.append(proc.pid)

    pidfile.write_text(",".join(str(p) for p in pids), encoding="utf-8")
    sys.stderr.write(f"[simulate.cpu_hog] Started {len(pids)} worker processes: {pids}\n")
    return pids


def stop_cpu_hog():
    """Stop all active CPU hog worker processes."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    pidfile = sandbox / "run" / "cpu_hog.pid"
    if not pidfile.is_file():
        return

    try:
        content = pidfile.read_text(encoding="utf-8").strip()
        if content:
            pids = [int(p) for p in content.split(",") if p.strip()]
            for pid in pids:
                try:
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
        sys.stderr.write("[simulate.cpu_hog] Stopped CPU hog workers.\n")


def main():
    parser = argparse.ArgumentParser(description="CPU Hog Simulator")
    parser.add_argument("--stop", action="store_true", help="Stop running CPU hog workers")
    parser.add_argument("--workers", type=int, default=2, help="Number of busy workers")
    parser.add_argument("--infraops-sim", action="store_true", help="Simulation marker")
    args = parser.parse_args()

    if args.stop:
        stop_cpu_hog()
    else:
        start_cpu_hog(num_workers=args.workers)


if __name__ == "__main__":
    main()
