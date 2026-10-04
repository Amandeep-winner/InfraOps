"""Network connectivity and listening port collector."""

import platform
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class ConnectivityCollector(BaseCollector):
    """Monitors TCP target reachability, ICMP ping, and listening port consistency."""

    name = "connectivity"

    def _check_tcp(self, host: str, port: int, timeout: float = 2.0) -> Tuple[bool, float, str]:
        start = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            latency_ms = round((time.time() - start) * 1000.0, 2)
            s.close()
            return True, latency_ms, "connected"
        except socket.timeout:
            return False, timeout * 1000.0, "timeout"
        except ConnectionRefusedError:
            return False, round((time.time() - start) * 1000.0, 2), "refused"
        except OSError as e:
            return False, round((time.time() - start) * 1000.0, 2), f"unreachable: {e}"
        finally:
            s.close()

    def _check_ping(self, target: str) -> Tuple[bool, float, str]:
        start = time.time()
        is_win = platform.system().lower() == "windows"
        cmd = (
            ["ping", "-n", "1", "-w", "1000", target]
            if is_win
            else ["ping", "-c", "1", "-W", "1", target]
        )
        try:
            res = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3
            )
            latency = round((time.time() - start) * 1000.0, 2)
            if res.returncode == 0:
                return True, latency, "icmp"
        except Exception:
            pass

        # Fallback to TCP probe on port 80/443
        tcp_up, lat, _ = self._check_tcp(target, 80, timeout=1.0)
        return tcp_up, lat, "tcp"

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        tcp_findings: List[Dict[str, Any]] = []

        # TCP Targets
        tcp_targets = self.config.get("tcp_targets", [])
        for target in tcp_targets:
            name = target.get("name", "tcp_target")
            host = target.get("host", "127.0.0.1")
            port = int(target.get("port", 80))

            up, lat_ms, status = self._check_tcp(host, port)
            metrics.append(
                MetricPoint(
                    name="conn.tcp_up",
                    value=1.0 if up else 0.0,
                    labels={"name": name},
                    ts=now,
                )
            )
            metrics.append(
                MetricPoint(
                    name="conn.tcp_latency_ms",
                    value=float(lat_ms),
                    labels={"name": name},
                    ts=now,
                )
            )
            tcp_findings.append(
                {"name": name, "host": host, "port": port, "up": up, "status": status}
            )

        # Ping Targets
        ping_targets = self.config.get("ping_targets", ["127.0.0.1"])
        for pt in ping_targets:
            up, lat_ms, method = self._check_ping(pt)
            metrics.append(
                MetricPoint(
                    name="conn.ping_up",
                    value=1.0 if up else 0.0,
                    labels={"target": pt},
                    ts=now,
                )
            )
            metrics.append(
                MetricPoint(
                    name="conn.ping_ms",
                    value=float(lat_ms),
                    labels={"target": pt},
                    ts=now,
                )
            )

        # Port listening check
        expected_ports = set(self.config.get("ports_expected_listening", []))
        actual_ports = set()
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.status == psutil.CONN_LISTEN and c.laddr:
                    actual_ports.add(c.laddr.port)
        except Exception:
            pass

        missing_ports = expected_ports - actual_ports
        unexpected_ports = actual_ports - expected_ports if expected_ports else set()

        metrics.append(
            MetricPoint(
                name="ports.expected_missing",
                value=float(len(missing_ports)),
                ts=now,
            )
        )
        metrics.append(
            MetricPoint(
                name="ports.unexpected_listening",
                value=float(len(unexpected_ports)),
                ts=now,
            )
        )

        snapshot = SnapshotPayload(
            kind="connectivity",
            payload={
                "tcp_targets": tcp_findings,
                "listening_ports": sorted(list(actual_ports)),
                "expected_ports": sorted(list(expected_ports)),
                "missing_ports": sorted(list(missing_ports)),
            },
            ts=now,
        )

        return metrics, snapshot, []
