"""InfraOps monitoring agent entry point and scheduler."""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from infraops.agent.collectors.base import BaseCollector
from infraops.agent.collectors.connectivity import ConnectivityCollector
from infraops.agent.collectors.cpu import CpuCollector
from infraops.agent.collectors.disk import DiskCollector
from infraops.agent.collectors.dns import DnsCollector
from infraops.agent.collectors.http import HttpCollector
from infraops.agent.collectors.logs import LogCollector
from infraops.agent.collectors.memory import MemoryCollector
from infraops.agent.collectors.network import NetworkCollector
from infraops.agent.collectors.permissions import PermissionCollector
from infraops.agent.collectors.processes import ProcessCollector
from infraops.agent.collectors.services import ServiceCollector
from infraops.agent.collectors.ssh_security import SshSecurityCollector
from infraops.agent.shipper import Shipper
from infraops.common.config import get_settings, load_yaml
from infraops.common.logging import setup_logger
from infraops.common.schemas import IngestBatch, LogEvent, MetricPoint, SnapshotPayload

logger = setup_logger("infraops.agent")


def _remap_sandbox_paths(obj: Any, sandbox_root: Path) -> Any:
    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("./sandbox") or s.startswith(".\\sandbox"):
            rel = s[9:].lstrip("/\\")
            return str(sandbox_root / rel)
        elif s.startswith("sandbox/") or s.startswith("sandbox\\"):
            rel = s[8:].lstrip("/\\")
            return str(sandbox_root / rel)
        return obj
    elif isinstance(obj, dict):
        return {k: _remap_sandbox_paths(v, sandbox_root) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_remap_sandbox_paths(v, sandbox_root) for v in obj]
    return obj


class Agent:
    """Orchestrates collectors, builds batches, and delegates shipping."""

    def __init__(
        self, config_path: Optional[str] = None, host_id_override: Optional[str] = None
    ) -> None:
        self.settings = get_settings()
        self.host_id = host_id_override or self.settings.get_effective_host_id()
        self.config_path = config_path or "config/agent.yaml"
        self.config: Dict[str, Any] = {}
        if Path(self.config_path).is_file():
            self.config = load_yaml(self.config_path)
            self.config = _remap_sandbox_paths(self.config, self.settings.get_sandbox_path())

        self.interval = float(self.config.get("interval_seconds", 5))
        self.fast_collectors: List[BaseCollector] = [
            CpuCollector(self.config),
            MemoryCollector(self.config),
            DiskCollector(self.config.get("disk", {})),
            NetworkCollector(self.config),
            ProcessCollector(self.config),
            ServiceCollector(self.config),
            LogCollector(self.config.get("logs", {})),
            ConnectivityCollector(self.config.get("network", {})),
            DnsCollector(self.config.get("dns", {})),
            HttpCollector(self.config.get("http", {})),
        ]

        self.slow_collectors: List[BaseCollector] = [
            SshSecurityCollector(self.config.get("ssh_security", {})),
            PermissionCollector(self.config.get("permissions", {})),
        ]
        self.slow_interval = 60.0
        self.last_slow_run = 0.0

        self.shipper = Shipper(
            server_url=self.settings.server_url,
            api_key=self.settings.api_key,
            spool_dir=Path(self.settings.sandbox_dir) / "spool",
        )

    def run_collection(self, include_slow: bool = True) -> IngestBatch:
        """Run collectors and assemble an IngestBatch."""
        now = time.time()
        all_metrics: List[MetricPoint] = [
            MetricPoint(name="agent.up", value=1.0, labels={"host_id": self.host_id}, ts=now)
        ]
        all_snapshots: List[SnapshotPayload] = []
        all_logs: List[LogEvent] = []

        # Fast collectors (executed concurrently)
        def _run_col(col):
            try:
                return col.collect()
            except Exception as e:
                logger.warning("Collector '%s' failed: %s", col.name, e)
                return [], None, []

        with ThreadPoolExecutor(max_workers=min(len(self.fast_collectors), 8)) as pool:
            for metrics, snapshot, logs in pool.map(_run_col, self.fast_collectors):
                all_metrics.extend(metrics)
                if snapshot:
                    all_snapshots.append(snapshot)
                all_logs.extend(logs)

        # Slow collectors
        if include_slow or (now - self.last_slow_run >= self.slow_interval):
            for collector in self.slow_collectors:
                try:
                    metrics, snapshot, logs = collector.collect()
                    all_metrics.extend(metrics)
                    if snapshot:
                        all_snapshots.append(snapshot)
                    all_logs.extend(logs)
                except Exception as e:
                    logger.warning("Slow collector '%s' failed: %s", collector.name, e)
            self.last_slow_run = now

        return IngestBatch(
            host_id=self.host_id,
            ts=now,
            metrics=all_metrics,
            snapshots=all_snapshots,
            log_events=all_logs,
        )

    def start(self) -> None:
        """Start regular periodic collection and shipping loop."""
        logger.info(
            "Starting InfraOps Agent for host '%s' (interval=%ss)", self.host_id, self.interval
        )
        self.shipper.register_host(self.host_id)

        while True:
            try:
                batch = self.run_collection(include_slow=False)
                self.shipper.ship(batch)
            except KeyboardInterrupt:
                logger.info("Agent stopped by user.")
                break
            except Exception as e:
                logger.error("Error in agent collection loop: %s", e)
            time.sleep(self.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="InfraOps Monitoring Agent")
    parser.add_argument(
        "--once", action="store_true", help="Run a single collection and print JSON to stdout"
    )
    parser.add_argument("--host-id", type=str, default=None, help="Override host identifier")
    parser.add_argument("--config", type=str, default=None, help="Path to agent configuration YAML")
    args = parser.parse_args()

    agent = Agent(config_path=args.config, host_id_override=args.host_id)

    if args.once:
        batch = agent.run_collection(include_slow=True)
        print(batch.model_dump_json(indent=2))
        sys.exit(0)
    else:
        agent.start()


if __name__ == "__main__":
    main()
