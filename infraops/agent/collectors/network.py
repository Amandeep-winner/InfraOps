"""Network metrics collector (traffic counters, errors, active TCP sockets)."""

import time
from typing import List, Optional, Tuple

import psutil

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class NetworkCollector(BaseCollector):
    """Collects network throughput, packet errors/drops, and TCP socket counts."""

    name = "network"

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []

        try:
            net_io = psutil.net_io_counters()
            if net_io:
                metrics.append(
                    MetricPoint(name="net.bytes_sent", value=float(net_io.bytes_sent), ts=now)
                )
                metrics.append(
                    MetricPoint(name="net.bytes_recv", value=float(net_io.bytes_recv), ts=now)
                )
                metrics.append(MetricPoint(name="net.errin", value=float(net_io.errin), ts=now))
                metrics.append(MetricPoint(name="net.errout", value=float(net_io.errout), ts=now))
                metrics.append(MetricPoint(name="net.dropin", value=float(net_io.dropin), ts=now))
                metrics.append(MetricPoint(name="net.dropout", value=float(net_io.dropout), ts=now))
        except Exception:
            pass

        # TCP connection state counts
        tcp_est = 0
        tcp_listen = 0
        try:
            conns = psutil.net_connections(kind="tcp")
            for c in conns:
                if c.status == psutil.CONN_ESTABLISHED:
                    tcp_est += 1
                elif c.status == psutil.CONN_LISTEN:
                    tcp_listen += 1
        except Exception:
            # Fallback if unprivileged
            pass

        metrics.append(MetricPoint(name="net.tcp_established", value=float(tcp_est), ts=now))
        metrics.append(MetricPoint(name="net.tcp_listen", value=float(tcp_listen), ts=now))

        return metrics, None, []
