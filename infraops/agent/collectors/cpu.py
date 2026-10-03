"""CPU metric collector (usage percent, load averages, core count)."""

import time
from typing import List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class CpuCollector(BaseCollector):
    """Gathers CPU utilization, load averages, and core counts."""

    name = "cpu"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        # Prime psutil CPU percent calculation so first call doesn't return 0.0
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []

        try:
            cpu_pct = float(psutil.cpu_percent(interval=0.1))
        except Exception:
            cpu_pct = 0.0
        metrics.append(MetricPoint(name="cpu.percent", value=cpu_pct, ts=now))

        # Core count
        core_count = psutil.cpu_count(logical=True) or 1
        metrics.append(MetricPoint(name="cpu.count", value=float(core_count), ts=now))

        # Load averages (Linux/Unix); fallback on Windows
        try:
            load1, load5, load15 = psutil.getloadavg()
        except (AttributeError, OSError):
            load1, load5, load15 = (cpu_pct / 100.0, cpu_pct / 100.0, cpu_pct / 100.0)

        metrics.append(MetricPoint(name="cpu.load1", value=float(load1), ts=now))
        metrics.append(MetricPoint(name="cpu.load5", value=float(load5), ts=now))
        metrics.append(MetricPoint(name="cpu.load15", value=float(load15), ts=now))

        return metrics, None, []
