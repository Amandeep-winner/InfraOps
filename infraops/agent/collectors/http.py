"""HTTP/HTTPS health and TLS certificate expiry collector."""

import datetime
import socket
import ssl
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class HttpCollector(BaseCollector):
    """Monitors HTTP endpoints for status codes, latency, and TLS cert expiration."""

    name = "http"

    def _get_tls_days_remaining(self, hostname: str, port: int = 443) -> Optional[float]:
        try:
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=2.0) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if not cert:
                        return None
                    not_after_str = cert.get("notAfter")
                    if not not_after_str:
                        return None
                    # e.g. 'May 15 12:00:00 2026 GMT'
                    expire_date = datetime.datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
                    remaining = (expire_date - datetime.datetime.utcnow()).total_seconds() / 86400.0
                    return round(max(0.0, remaining), 1)
        except Exception:
            return None

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        checks_data: List[Dict[str, Any]] = []

        checks = self.config.get("checks", [])
        for chk in checks:
            name = chk.get("name", "http_check")
            url = chk.get("url", "http://127.0.0.1:8081/health")
            expect_status = int(chk.get("expect_status", 200))
            timeout = float(chk.get("timeout", 2.0))

            start = time.time()
            status_code = 0
            up = False
            latency_ms = 0.0

            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.get(url)
                    status_code = resp.status_code
                    latency_ms = round((time.time() - start) * 1000.0, 2)
                    up = status_code == expect_status
            except Exception:
                latency_ms = round((time.time() - start) * 1000.0, 2)
                up = False

            metrics.append(
                MetricPoint(name="http.up", value=1.0 if up else 0.0, labels={"name": name}, ts=now)
            )
            metrics.append(
                MetricPoint(
                    name="http.status", value=float(status_code), labels={"name": name}, ts=now
                )
            )
            metrics.append(
                MetricPoint(
                    name="http.latency_ms", value=float(latency_ms), labels={"name": name}, ts=now
                )
            )

            # Check TLS expiry if HTTPS
            parsed = urlparse(url)
            tls_days = None
            if parsed.scheme == "https":
                port = parsed.port or 443
                tls_days = self._get_tls_days_remaining(parsed.hostname or "", port)
                if tls_days is not None:
                    metrics.append(
                        MetricPoint(
                            name="tls.days_to_expiry",
                            value=float(tls_days),
                            labels={"name": name},
                            ts=now,
                        )
                    )

            checks_data.append(
                {
                    "name": name,
                    "url": url,
                    "status_code": status_code,
                    "up": up,
                    "latency_ms": latency_ms,
                    "tls_days_remaining": tls_days,
                }
            )

        snapshot = SnapshotPayload(kind="http", payload={"checks": checks_data}, ts=now)
        return metrics, snapshot, []
