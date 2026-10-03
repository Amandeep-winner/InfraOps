"""Service outage simulator: kills or restarts the managed demo service."""

import argparse
import sys

from infraops.demo.supervisor import ServiceManager


def trigger_service_down():
    """Terminate the managed demo service process."""
    mgr = ServiceManager("demo-service")
    mgr.stop()
    sys.stderr.write("[simulate.service_down] Stopped demo-service.\n")


def restore_service():
    """Restart the managed demo service process."""
    mgr = ServiceManager("demo-service")
    pid = mgr.start()
    sys.stderr.write(f"[simulate.service_down] Restored demo-service (PID {pid}).\n")


def main():
    parser = argparse.ArgumentParser(description="Service Outage Simulator")
    parser.add_argument("--stop", action="store_true", help="Restore the service")
    args = parser.parse_args()

    if args.stop:
        restore_service()
    else:
        trigger_service_down()


if __name__ == "__main__":
    main()
