"""SQLAlchemy database models for InfraOps."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class."""


class Host(Base):
    """Monitored host record."""

    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="127.0.0.1")
    os: Mapped[str] = mapped_column(String(128), nullable=False, default="linux")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="vm")  # ec2, docker, vm
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="up")  # up, stale, down
    tags: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class Metric(Base):
    """Raw time-series metric data point."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(String(64), ForeignKey("hosts.id"), nullable=False)
    ts: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    labels: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("idx_metrics_host_name_ts", "host_id", "name", "ts"),)


class Snapshot(Base):
    """Point-in-time structured host snapshot."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(String(64), ForeignKey("hosts.id"), nullable=False)
    ts: Mapped[float] = mapped_column(Float, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class LogEventModel(Base):
    """Detected log event entry."""

    __tablename__ = "log_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[str] = mapped_column(String(64), ForeignKey("hosts.id"), nullable=False)
    ts: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(32), default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    matched_pattern: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Alert(Base):
    """Evaluated alert instance."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    host_id: Mapped[str] = mapped_column(String(64), ForeignKey("hosts.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="firing")  # firing, resolved
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    incident_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class Incident(Base):
    """Sequential incident management record (INC-001)."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # INC-001
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    host_id: Mapped[str] = mapped_column(String(64), ForeignKey("hosts.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # P1 - P4
    state: Mapped[str] = mapped_column(String(32), default="DETECTED")
    sop_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolution_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="auto")  # auto, manual


class IncidentEvent(Base):
    """Chronological timeline event for an incident."""

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(32), ForeignKey("incidents.id"), nullable=False)
    ts: Mapped[float] = mapped_column(Float, nullable=False)
    phase: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # detect, investigate, identify, remediate, verify, close, note
    actor: Mapped[str] = mapped_column(String(32), nullable=False)  # system, sop, human
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class SopRun(Base):
    """SOP execution run record."""

    __tablename__ = "sop_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(32), ForeignKey("incidents.id"), nullable=False)
    sop_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    step_results: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


SOPRun = SopRun


class Approval(Base):
    """Manual L1 intervention approval request."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(32), ForeignKey("incidents.id"), nullable=False)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="pending")  # pending, approved, rejected
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
