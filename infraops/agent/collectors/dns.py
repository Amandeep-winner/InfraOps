"""DNS resolution and resolver health collector."""

import time
from pathlib import Path
from typing import List, Optional, Tuple

import dns.resolver

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class DnsCollector(BaseCollector):
    """Monitors DNS record resolution, response latency, and resolver availability."""

    name = "dns"

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        findings = []

        fault_flag_path = self.config.get("fault_flag", "./sandbox/faults/dns_fail")
        fault_active = Path(fault_flag_path).exists()

        custom_resolvers = self.config.get("resolvers", ["system"])
        res = dns.resolver.Resolver()
        res.lifetime = 1.5

        if fault_active:
            # Simulated failure: route DNS requests to dead port
            res.nameservers = ["127.0.0.1"]
            res.port = 5399
        elif any(r != "system" for r in custom_resolvers):
            res.nameservers = [r for r in custom_resolvers if r != "system"]

        names = self.config.get("names", ["localhost", "example.com"])
        for name in names:
            start = time.time()
            up = False
            answers_list = []
            try:
                if name == "localhost":
                    answers_list = ["127.0.0.1"]
                    up = not fault_active
                else:
                    ans = res.resolve(name, "A")
                    answers_list = [str(r) for r in ans]
                    up = True
            except Exception:
                up = False

            latency_ms = round((time.time() - start) * 1000.0, 2)
            metrics.append(
                MetricPoint(name="dns.up", value=1.0 if up else 0.0, labels={"name": name}, ts=now)
            )
            metrics.append(
                MetricPoint(
                    name="dns.latency_ms", value=float(latency_ms), labels={"name": name}, ts=now
                )
            )
            findings.append(
                {"name": name, "up": up, "answers": answers_list, "latency_ms": latency_ms}
            )

        resolver_name = "dead:5399" if fault_active else "system"
        metrics.append(
            MetricPoint(
                name="dns.resolver_up",
                value=0.0 if fault_active else 1.0,
                labels={"resolver": resolver_name},
                ts=now,
            )
        )

        snapshot = SnapshotPayload(
            kind="dns", payload={"queries": findings, "fault_active": fault_active}, ts=now
        )
        return metrics, snapshot, []
