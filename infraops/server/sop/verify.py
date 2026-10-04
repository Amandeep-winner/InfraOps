"""SOP verification predicates for metrics, HTTP endpoints, and services."""

import time
from typing import Any, Dict

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.demo.supervisor import ServiceManager
from infraops.server.models import Metric


def verify_metric_condition(params: Dict[str, Any], db: Session, host_id: str) -> bool:
    """Verify that a metric condition is satisfied within a timeout window."""
    metric_name = params.get("metric")
    op = params.get("op", "<")
    threshold = float(params.get("threshold", 70.0))
    within_seconds = float(params.get("within_seconds", 30.0))
    sustain_seconds = float(params.get("sustain_seconds", 0.0))

    deadline = time.time() + within_seconds
    consecutive_ok_start = None

    while time.time() <= deadline:
        db.expire_all()
        # Query latest metric for host
        m = db.scalars(
            select(Metric)
            .where(Metric.host_id == host_id, Metric.name == metric_name)
            .order_by(Metric.ts.desc())
        ).first()

        ok = False
        if m is not None:
            if op == "<":
                ok = m.value < threshold
            elif op == "<=":
                ok = m.value <= threshold
            elif op == ">":
                ok = m.value > threshold
            elif op == ">=":
                ok = m.value >= threshold
            elif op == "==":
                ok = abs(m.value - threshold) < 1e-4

        if ok:
            if sustain_seconds <= 0.0:
                return True
            if consecutive_ok_start is None:
                consecutive_ok_start = time.time()
            elif time.time() - consecutive_ok_start >= sustain_seconds:
                return True
        else:
            consecutive_ok_start = None

        time.sleep(0.5)

    return False


def verify_http_endpoint(params: Dict[str, Any]) -> bool:
    """Check that an HTTP endpoint responds with the expected status code."""
    url = params.get("url", "http://127.0.0.1:8081/health")
    expect_status = int(params.get("expect_status", 200))
    timeout = float(params.get("within_seconds", 5.0))

    deadline = time.time() + timeout
    while time.time() <= deadline:
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(url)
                if res.status_code == expect_status:
                    return True
        except Exception:
            pass
        time.sleep(0.5)

    return False


def verify_service_running(params: Dict[str, Any]) -> bool:
    """Verify that a declared managed service is alive."""
    svc_name = params.get("service", "demo-service")
    mgr = ServiceManager(svc_name)
    return mgr.is_running()
