"""Unified simulation CLI runner."""

import argparse

from scripts.simulate import (
    cpu_hog,
    disk_fill,
    dns_failure,
    mem_hog,
    net_connectivity,
    service_down,
)

SIMULATORS = {
    "cpu": cpu_hog,
    "high_cpu": cpu_hog,
    "mem": mem_hog,
    "memory": mem_hog,
    "high_memory": mem_hog,
    "disk": disk_fill,
    "disk_fill": disk_fill,
    "service": service_down,
    "service_down": service_down,
    "dns": dns_failure,
    "dns_failure": dns_failure,
    "net": net_connectivity,
    "network": net_connectivity,
    "net_connectivity": net_connectivity,
}


def main():
    parser = argparse.ArgumentParser(description="InfraOps Incident Simulator Runner")
    parser.add_argument("name", choices=list(SIMULATORS.keys()), help="Name of incident simulation")
    parser.add_argument(
        "--stop", action="store_true", help="Stop the simulation and restore service"
    )
    parser.add_argument("--workers", type=int, default=2, help="Workers for CPU sim")
    parser.add_argument("--cap-mb", type=int, default=150, help="Cap for memory sim")
    parser.add_argument("--target-mb", type=int, default=95, help="Target MB for disk fill sim")
    args = parser.parse_args()

    module = SIMULATORS[args.name]
    if args.stop:
        if hasattr(module, "stop_cpu_hog"):
            module.stop_cpu_hog()
        elif hasattr(module, "stop_mem_hog"):
            module.stop_mem_hog()
        elif hasattr(module, "stop_disk_fill"):
            module.stop_disk_fill()
        elif hasattr(module, "restore_service"):
            module.restore_service()
        elif hasattr(module, "restore_dns"):
            module.restore_dns()
        elif hasattr(module, "restore_network"):
            module.restore_network()
    else:
        if hasattr(module, "start_cpu_hog"):
            module.start_cpu_hog(num_workers=args.workers)
        elif hasattr(module, "start_mem_hog"):
            module.start_mem_hog(cap_mb=args.cap_mb)
        elif hasattr(module, "start_disk_fill"):
            module.start_disk_fill(target_mb=args.target_mb)
        elif hasattr(module, "trigger_service_down"):
            module.trigger_service_down()
        elif hasattr(module, "trigger_dns_failure"):
            module.trigger_dns_failure()
        elif hasattr(module, "trigger_net_outage"):
            module.trigger_net_outage()


if __name__ == "__main__":
    main()
