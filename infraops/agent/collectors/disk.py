"""Disk and virtual volume metric collector."""

import os
import time
from pathlib import Path
from typing import List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class DiskCollector(BaseCollector):
    """Collects filesystem space, inodes, IO counters, and sandbox virtual volumes."""

    name = "disk"

    def _get_dir_size_bytes(self, path: Path) -> int:
        """Calculate total size in bytes of all files in a directory tree."""
        if not path.exists():
            return 0
        total = 0
        try:
            for root, _, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []

        # Standard filesystem mounts
        configured_paths = self.config.get("paths", ["/"])
        for p in configured_paths:
            try:
                usage = psutil.disk_usage(p)
                metrics.append(
                    MetricPoint(
                        name="disk.percent", value=float(usage.percent), labels={"mount": p}, ts=now
                    )
                )
                free_mb = round(usage.free / (1024 * 1024), 2)
                metrics.append(
                    MetricPoint(
                        name="disk.free_mb", value=float(free_mb), labels={"mount": p}, ts=now
                    )
                )

                # Inode percentage (Unix only)
                inode_pct = 0.0
                if hasattr(os, "statvfs"):
                    try:
                        st = os.statvfs(p)
                        if st.f_files > 0:
                            used_inodes = st.f_files - st.f_ffree
                            inode_pct = round((used_inodes / st.f_files) * 100.0, 2)
                    except OSError:
                        inode_pct = 0.0
                metrics.append(
                    MetricPoint(
                        name="disk.inode_percent",
                        value=float(inode_pct),
                        labels={"mount": p},
                        ts=now,
                    )
                )
            except Exception:
                pass

        # Virtual sandbox volumes (e.g. sandbox-data capped at capacity_mb)
        virtual_volumes = self.config.get("virtual_volumes", [])
        for vol in virtual_volumes:
            name = vol.get("name", "vol")
            vol_path = Path(vol.get("path", "./sandbox/data"))
            capacity_mb = float(vol.get("capacity_mb", 100))
            used_bytes = self._get_dir_size_bytes(vol_path)
            used_mb = used_bytes / (1024 * 1024)
            pct = min(100.0, round((used_mb / max(capacity_mb, 1.0)) * 100.0, 2))
            metrics.append(
                MetricPoint(
                    name="disk.vol.percent", value=float(pct), labels={"name": name}, ts=now
                )
            )

        # IO counters
        try:
            io = psutil.disk_io_counters()
            if io:
                metrics.append(
                    MetricPoint(name="disk.io_read_bytes", value=float(io.read_bytes), ts=now)
                )
                metrics.append(
                    MetricPoint(name="disk.io_write_bytes", value=float(io.write_bytes), ts=now)
                )
        except Exception:
            pass

        return metrics, None, []
