"""Network outage simulator: stops the upstream dependency listener on port 8082."""

import argparse
import sys

from infraops.demo.supervisor import ServiceManager


def trigger_net_outage():
    """Stop the upstream TCP listener."""
    mgr = ServiceManager("demo-upstream")
    mgr.stop()
    sys.stderr.write(
        "[simulate.net_connectivity] Stopped demo-upstream TCP listener on port 8082.\n"
    )


def restore_network():
    """Restart the upstream TCP listener."""
    mgr = ServiceManager("demo-upstream")
    pid = mgr.start()
    sys.stderr.write(
        f"[simulate.net_connectivity] Restored demo-upstream on port 8082 (PID {pid}).\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Network Upstream Connectivity Simulator")
    parser.add_argument("--stop", action="store_true", help="Restore upstream TCP listener")
    args = parser.parse_args()

    if args.stop:
        restore_network()
    else:
        trigger_net_outage()


if __name__ == "__main__":
    main()
