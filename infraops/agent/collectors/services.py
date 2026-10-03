"""Service availability collector (pidfile supervisor & systemd)."""

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class ServiceCollector(BaseCollector):
    """Monitors configured daemon services via pidfiles or systemctl."""

    name = "services"

    def _check_pidfile_service(self, svc_config: Dict[str, Any]) -> Tuple[bool, str]:
        pidfile = svc_config.get("pidfile")
        if not pidfile:
            return False, "pidfile path not specified"

        path = Path(pidfile)
        if not path.is_file():
            return False, "pidfile missing"

        try:
            pid_str = path.read_text(encoding="utf-8").strip()
            pid = int(pid_str)
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    return True, f"running (pid {pid})"
            return False, f"pid {pid} not running"
        except Exception as e:
            return False, f"error reading pidfile: {e}"

    def _check_systemd_service(self, svc_config: Dict[str, Any]) -> Tuple[bool, str]:
        svc_name = svc_config.get("name")
        if not shutil.which("systemctl"):
            return False, "systemctl unavailable"
        try:
            res = subprocess.run(
                ["systemctl", "is-active", svc_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            is_active = res.stdout.strip() == "active"
            return is_active, res.stdout.strip()
        except Exception as e:
            return False, f"systemctl error: {e}"

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        statuses: List[Dict[str, Any]] = []

        services = self.config.get("services", [])
        for svc in services:
            name = svc.get("name", "unknown")
            manager = svc.get("manager", "pidfile")

            if manager == "systemd":
                is_up, status_desc = self._check_systemd_service(svc)
            else:
                is_up, status_desc = self._check_pidfile_service(svc)

            metrics.append(
                MetricPoint(
                    name="service.up", value=1.0 if is_up else 0.0, labels={"name": name}, ts=now
                )
            )
            statuses.append(
                {
                    "name": name,
                    "manager": manager,
                    "up": is_up,
                    "status": status_desc,
                }
            )

        snapshot = SnapshotPayload(kind="services", payload={"services": statuses}, ts=now)
        return metrics, snapshot, []
