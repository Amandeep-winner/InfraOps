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

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        top_n = int(self.config.get("top_n_processes", 5))

        total_procs = 0
        zombies = 0
        proc_list: List[Dict[str, Any]] = []

        # Iterate over running processes safely
        for p in psutil.process_iter(
            attrs=["pid", "name", "username", "cpu_percent", "memory_info", "cmdline", "status"]
        ):
            try:
                info = p.info
                total_procs += 1
                if info.get("status") == psutil.STATUS_ZOMBIE:
                    zombies += 1

                pid = info.get("pid")
                name = info.get("name") or "unknown"
                user = info.get("username") or "unknown"
                cpu = float(info.get("cpu_percent") or 0.0)
                mem_info = info.get("memory_info")
                rss_mb = round(mem_info.rss / (1024 * 1024), 2) if mem_info else 0.0
                cmdline = info.get("cmdline") or []
                cmdline_str = " ".join(cmdline)

                # Check if process carries simulation sandbox marker
                marked = False
                if pid:
                    marked = is_sandbox_process(pid)

                proc_list.append(
                    {
                        "pid": pid,
                        "name": name,
                        "user": user,
                        "cpu": cpu,
                        "rss_mb": rss_mb,
                        "cmdline": cmdline_str,
                        "sandbox_marked": marked,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        metrics.append(MetricPoint(name="proc.count", value=float(total_procs), ts=now))
        metrics.append(MetricPoint(name="proc.zombies", value=float(zombies), ts=now))

        # Sort top N by CPU and memory
        top_cpu = sorted(proc_list, key=lambda x: x["cpu"], reverse=True)[:top_n]
        top_mem = sorted(proc_list, key=lambda x: x["rss_mb"], reverse=True)[:top_n]

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

        return metrics, snapshot, []
