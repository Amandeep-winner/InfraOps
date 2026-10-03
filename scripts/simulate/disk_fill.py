"""Disk exhaustion simulator: writes large bloated log files into sandbox/data/."""

import argparse
import sys
from pathlib import Path

from infraops.common.config import get_settings


def start_disk_fill(target_mb: int = 95):
    """Write large dummy log files into sandbox/data/ to simulate volume exhaustion."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    data_dir = sandbox / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    chunk = b"X" * (1024 * 1024)  # 1MB chunk
    num_files = 3
    mb_per_file = target_mb // num_files

    created_files = []
    for i in range(num_files):
        log_file = data_dir / f"sim_bloat_{i + 1}.log"
        with log_file.open("wb") as f:
            for _ in range(mb_per_file):
                f.write(chunk)
        created_files.append(log_file)

    sys.stderr.write(
        f"[simulate.disk_fill] Created {len(created_files)} files totaling ~{target_mb}MB in {data_dir}\n"
    )


def stop_disk_fill():
    """Remove simulated bloated log files from sandbox/data/."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    data_dir = sandbox / "data"
    if not data_dir.is_dir():
        return

    removed = 0
    for f in data_dir.glob("sim_bloat_*.log"):
        f.unlink(missing_ok=True)
        removed += 1

    sys.stderr.write(f"[simulate.disk_fill] Cleaned up {removed} simulated log files.\n")


def main():
    parser = argparse.ArgumentParser(description="Disk Fill Simulator")
    parser.add_argument("--stop", action="store_true", help="Remove bloated log files")
    parser.add_argument("--target-mb", type=int, default=95, help="Total MB to write")
    args = parser.parse_args()

    if args.stop:
        stop_disk_fill()
    else:
        start_disk_fill(target_mb=args.target_mb)


if __name__ == "__main__":
    main()
