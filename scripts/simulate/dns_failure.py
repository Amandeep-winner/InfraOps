"""DNS failure simulator: injects resolver fault flag in sandbox/faults/."""

import argparse
import sys
from pathlib import Path

from infraops.common.config import get_settings


def trigger_dns_failure():
    """Create fault flag file causing agent DNS collector to probe dead resolver."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    faults_dir = sandbox / "faults"
    faults_dir.mkdir(parents=True, exist_ok=True)

    flag = faults_dir / "dns_fail"
    flag.write_text("1", encoding="utf-8")
    sys.stderr.write(f"[simulate.dns_failure] Created DNS fault flag at {flag}\n")


def restore_dns():
    """Remove fault flag file restoring standard resolver behavior."""
    settings = get_settings()
    sandbox = Path(settings.sandbox_dir).resolve()
    flag = sandbox / "faults" / "dns_fail"
    if flag.exists():
        flag.unlink()
        sys.stderr.write("[simulate.dns_failure] Cleared DNS fault flag.\n")


def main():
    parser = argparse.ArgumentParser(description="DNS Failure Simulator")
    parser.add_argument("--stop", action="store_true", help="Restore normal DNS resolution")
    args = parser.parse_args()

    if args.stop:
        restore_dns()
    else:
        trigger_dns_failure()


if __name__ == "__main__":
    main()
