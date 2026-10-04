"""CloudWatch metrics publishing and alarm inspection module."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from infraops.server.aws.client import get_client, seed_mock_environment


def list_alarms() -> List[Dict[str, Any]]:
    """List CloudWatch alarms with evaluation states, thresholds, and metrics."""
    seed_mock_environment()
    cw = get_client("cloudwatch")
    resp = cw.describe_alarms()

    alarms = []
    for a in resp.get("MetricAlarms", []):
        alarms.append(
            {
                "alarm_name": a.get("AlarmName"),
                "state": a.get("StateValue", "INSUFFICIENT_DATA"),
                "state_reason": a.get("StateReason", ""),
                "metric_name": a.get("MetricName"),
                "namespace": a.get("Namespace"),
                "statistic": a.get("Statistic"),
                "threshold": a.get("Threshold"),
                "comparison_operator": a.get("ComparisonOperator"),
                "evaluation_periods": a.get("EvaluationPeriods"),
                "period": a.get("Period"),
                "description": a.get("AlarmDescription", ""),
                "state_updated": str(a.get("StateUpdatedTimestamp", "")),
            }
        )

    return alarms


def put_metric_data(
    namespace: str,
    metric_name: str,
    value: float,
    unit: str = "Percent",
    dimensions: Optional[List[Dict[str, str]]] = None,
) -> bool:
    """Publish a single metric datapoint to CloudWatch."""
    seed_mock_environment()
    cw = get_client("cloudwatch")
    metric_data: Dict[str, Any] = {
        "MetricName": metric_name,
        "Value": float(value),
        "Unit": unit,
        "Timestamp": datetime.now(timezone.utc),
    }
    if dimensions:
        metric_data["Dimensions"] = dimensions

    try:
        cw.put_metric_data(Namespace=namespace, MetricData=[metric_data])
        return True
    except Exception:
        return False


def publish_host_metrics(
    host_id: str,
    cpu_percent: Optional[float] = None,
    mem_percent: Optional[float] = None,
    disk_percent: Optional[float] = None,
) -> Dict[str, bool]:
    """Publish core system telemetry for a host into the InfraOps/Host CloudWatch namespace."""
    results = {}
    dims = [{"Name": "HostId", "Value": host_id}]
    namespace = "InfraOps/Host"

    if cpu_percent is not None:
        results["CPUPercent"] = put_metric_data(
            namespace, "CPUPercent", cpu_percent, "Percent", dims
        )
    if mem_percent is not None:
        results["MemPercent"] = put_metric_data(
            namespace, "MemPercent", mem_percent, "Percent", dims
        )
    if disk_percent is not None:
        results["DiskPercent"] = put_metric_data(
            namespace, "DiskPercent", disk_percent, "Percent", dims
        )

    return results
