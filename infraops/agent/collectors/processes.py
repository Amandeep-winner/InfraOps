"""Process metrics and top-N snapshot collector."""

import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.sandbox import is_sandbox_process
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class ProcessCollector(BaseCollector):
    """Monitors running processes, detects zombies, and records top-N resource consumers."""

    name = "processes"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._last_snapshot_time = 0.0
        self._cached_snapshot: Optional[SnapshotPayload] = None
        self._cached_total = 0
        self._cached_zombies = 0

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        top_n = int(self.config.get("top_n_processes", 5))

        # If collected within last 3 seconds, return cached snapshot with fast count
        if now - self._last_snapshot_time < 3.0 and self._cached_snapshot is not None:
            fast_count = float(len(psutil.pids()))
            metrics.append(MetricPoint(name="proc.count", value=fast_count, ts=now))
            metrics.append(
                MetricPoint(name="proc.zombies", value=float(self._cached_zombies), ts=now)
            )
            return metrics, self._cached_snapshot, []

        total_procs = 0
        zombies = 0
        proc_list: List[Dict[str, Any]] = []

        # Iterate over running processes safely with minimal attributes
        for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = p.info
                total_procs += 1
                pid = info.get("pid")
                name = info.get("name") or "unknown"
                cpu = float(info.get("cpu_percent") or 0.0)
                mem_info = info.get("memory_info")
                rss_mb = round(mem_info.rss / (1024 * 1024), 2) if mem_info else 0.0

                proc_list.append(
                    {
                        "pid": pid,
                        "name": name,
                        "user": "system",
                        "cpu": cpu,
                        "rss_mb": rss_mb,
                        "cmdline": "",
                        "sandbox_marked": False,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        metrics.append(MetricPoint(name="proc.count", value=float(total_procs), ts=now))
        metrics.append(MetricPoint(name="proc.zombies", value=float(zombies), ts=now))

        # Sort top N by CPU and memory
        top_cpu = sorted(proc_list, key=lambda x: x["cpu"], reverse=True)[:top_n]
        top_mem = sorted(proc_list, key=lambda x: x["rss_mb"], reverse=True)[:top_n]

        # Lazy enrichment: inspect cmdline and sandbox markers ONLY for top candidates
        for item in top_cpu + top_mem:
            pid = item.get("pid")
            if pid:
                item["sandbox_marked"] = is_sandbox_process(pid)
                try:
                    proc = psutil.Process(pid)
                    item["cmdline"] = " ".join(proc.cmdline())
                    try:
                        item["user"] = proc.username()
                    except Exception:
                        pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        snapshot = SnapshotPayload(
            kind="processes",
            payload={
                "total": total_procs,
                "zombies": zombies,
                "top_cpu": top_cpu,
                "top_mem": top_mem,
            },
            ts=now,
        )

        self._last_snapshot_time = now
        self._cached_snapshot = snapshot
        self._cached_total = total_procs
        self._cached_zombies = zombies

        return metrics, snapshot, []
