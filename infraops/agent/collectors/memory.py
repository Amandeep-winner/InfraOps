"""Memory and swap metric collector."""

import time
from typing import List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class MemoryCollector(BaseCollector):
    """Gathers virtual memory and swap statistics."""

    name = "memory"

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []

        vm = psutil.virtual_memory()
        metrics.append(MetricPoint(name="mem.percent", value=float(vm.percent), ts=now))
        metrics.append(
            MetricPoint(name="mem.used_mb", value=float(round(vm.used / (1024 * 1024), 2)), ts=now)
        )
        metrics.append(
            MetricPoint(
                name="mem.available_mb",
                value=float(round(vm.available / (1024 * 1024), 2)),
                ts=now,
            )
        )

        try:
            sm = psutil.swap_memory()
            swap_pct = float(sm.percent)
        except Exception:
            swap_pct = 0.0

        metrics.append(MetricPoint(name="swap.percent", value=swap_pct, ts=now))
        return metrics, None, []
