"""Shared Pydantic schemas for metrics, snapshots, logs, and API payloads."""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """Individual metric data point."""

    name: str = Field(..., description="Metric identifier, e.g. cpu.percent")
    value: float = Field(..., description="Numeric metric measurement")
    labels: Dict[str, str] = Field(default_factory=dict, description="Metric tags/dimensions")
    ts: float = Field(default_factory=time.time, description="Timestamp in epoch seconds")


class SnapshotPayload(BaseModel):
    """Point-in-time structured snapshot (e.g. processes, services, findings)."""

    kind: str = Field(..., description="Type of snapshot, e.g. processes, services, ssh")
    payload: Dict[str, Any] = Field(..., description="Structured snapshot content")
    ts: float = Field(default_factory=time.time, description="Timestamp in epoch seconds")


class LogEvent(BaseModel):
    """Categorized log event detected on a host."""

    source: str = Field(..., description="Log file or origin, e.g. demo-service")
    level: str = Field(default="INFO", description="Log level: INFO, WARN, ERROR, CRITICAL")
    message: str = Field(..., description="Raw or formatted log entry")
    matched_pattern: Optional[str] = Field(default=None, description="Regex pattern matched")
    ts: float = Field(default_factory=time.time, description="Timestamp in epoch seconds")


class IngestBatch(BaseModel):
    """Batch payload sent by an agent to the ingest API."""

    host_id: str = Field(..., description="Unique host identifier")
    ts: float = Field(default_factory=time.time, description="Batch creation timestamp")
    metrics: List[MetricPoint] = Field(default_factory=list)
    snapshots: List[SnapshotPayload] = Field(default_factory=list)
    log_events: List[LogEvent] = Field(default_factory=list)


class HostRegisterRequest(BaseModel):
    """Payload to register or update host metadata."""

    id: str = Field(..., description="Host ID")
    hostname: str = Field(..., description="Host network name")
    ip: str = Field(default="127.0.0.1", description="Primary host IP")
    os: str = Field(default="linux", description="Operating system details")
    kind: str = Field(default="vm", description="Infrastructure kind: ec2, docker, vm")
    tags: Dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class HostResponse(BaseModel):
    """Host details response."""

    id: str
    hostname: str
    ip: str
    os: str
    kind: str
    last_seen: datetime
    status: str
    tags: Dict[str, Any]


class ActionRequest(BaseModel):
    """Request payload sent to agent action dispatcher."""

    action: str = Field(..., description="Allowlisted action name")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action arguments")


class ActionResponse(BaseModel):
    """Response returned from action execution."""

    ok: bool
    output: Any
    duration_ms: float
    error: Optional[str] = None
