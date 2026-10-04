# InfraOps Architecture & System Design

This document details the architecture, engineering principles, data pipelines, and safety models governing the InfraOps platform.

---

## 1. High-Level System Architecture

InfraOps is structured around a distributed agent-server topology tailored for infrastructure monitoring and autonomous Level-1 (L1) incident remediation.
The platform decouples edge metric collection from centralized rule evaluation and remediation dispatching.

```
                          Target Infrastructure (Linux / Container / EC2)
                                                 │
                     ┌───────────────────────────┴───────────────────────────┐
                     ▼                                                       ▼
        Local Diagnostics (Bash)                              Agent Collectors (Python)
    (sys_snapshot, check_ports, etc.)                     (CPU, Mem, Disk, Net, Svc, Logs, etc.)
                     │                                                       │
                     └───────────────────────────┬───────────────────────────┘
                                                 ▼
                                     Agent Shipper & Action API
                                (Spooler, Backoff, Port 8099 Action API)
                                                 │
                             HTTPS / JSON Batch (X-API-Key Authentication)
                                                 ▼
                                      Central Server (FastAPI)
                     ┌───────────────────────────┼───────────────────────────┐
                     ▼                           ▼                           ▼
            SQLite WAL Store              Alert Evaluation             SOP Orchestrator
         (Hosts, Metrics, Alerts)       (Sustain & Flap Guard)     (State Machine, Actions)
                     │                           │                           │
                     └───────────────────────────┼───────────────────────────┘
                                                 ▼
                                NOC Web Dashboard & Cloud Integrations
                            (Jinja2 Views, S3 Reports, CloudWatch Metrics)
```

---

## 2. Core Architectural Components

### 2.1 Agent Layer (`infraops/agent/`)
The agent runs on monitored compute instances as a non-privileged daemon or periodic task.
Its primary responsibilities include:
- Multi-dimensional telemetry collection across 12 distinct collector categories.
- Local command execution through standard POSIX diagnostic scripts.
- Asynchronous metric transmission with local disk spooling during network interruptions.
- Exposing a token-authenticated action API on `127.0.0.1:8099` for targeted remediation commands.

### 2.2 Server Ingestion & Storage Layer (`infraops/server/`)
The central server is implemented using FastAPI and SQLAlchemy.
Key architectural properties include:
- High-concurrency SQLite database with Write-Ahead Logging (WAL) enabled (`PRAGMA journal_mode=WAL`).
- Structured downsampling and time-window queries for fast graph rendering.
- Strict API key verification via `X-API-Key` headers on all ingestion and mutation endpoints.

### 2.3 Alert Evaluation Engine (`infraops/server/alerting/`)
The alert engine evaluates incoming batches against declarative rules defined in YAML format.
Core features include:
- Sustained breach tracking with duration windows (`for_seconds`).
- Host-level alert deduplication and automated resolution when metrics recover.
- Flapping guards preventing alert churn under erratic workload conditions.
- Dead-host heartbeat monitoring identifying missing or stalled telemetry.

### 2.4 Incident State Machine & SOP Orchestrator (`infraops/server/sop/`, `incidents/`)
Incidents transition through a strict, auditable lifecycle:
`DETECTED` -> `INVESTIGATING` -> `IDENTIFIED` -> `REMEDIATING` -> `VERIFYING` -> `RESOLVED` -> `CLOSED`.
Features include:
- Sequential identifier generation (`INC-001`, `INC-002`) guarded by thread-level locks.
- Allowlisted action execution restricting operations to pre-approved diagnostic and remediation actions.
- Dual execution modes: Autonomous remediation or L1 guided manual mode requiring operator confirmation.
- Automatic retry on verification failure with fallback escalation to L2 engineering.

---

## 3. Safety Architecture & Sandbox Isolation

To guarantee that autonomous remediation cannot cause collateral host damage, InfraOps implements strict defense-in-depth guardrails:

### 3.1 Path Traversal & Symlink Guards (`infraops/common/sandbox.py`)
All file creation, log rotation, and deletion operations are confined to `INFRAOPS_SANDBOX_DIR` (default `./sandbox`).
- Path canonicalization resolves all intermediate symlinks and relative directory tokens.
- Parent directory escapes (`..`) trigger immediate exceptions.
- Real-world symlink target verification blocks symbolic link directory traversal.

### 3.2 Process Termination Guardrails
Process manipulation actions (`kill_process`, `renice_process`) enforce strict safety constraints:
- Protected system processes (PID 0, PID 1) are unconditionally protected.
- The monitoring agent and server processes can never terminate themselves or their parents.
- Target processes must contain approved sandbox markers in their process command lines or environment variables.

---

## 4. Cloud Integration Architecture (Mock & Live)

InfraOps interfaces with AWS infrastructure while maintaining offline capability:
- Mock mode leverages Moto to seed a realistic topology on startup.
- Resources include a VPC (`10.0.0.0/16`), public and private subnets, security groups, EC2 nodes, S3 buckets, IAM roles, and CloudWatch alarms.
- S3 bucket integration automatically archives markdown incident reports upon incident resolution.
- CloudWatch telemetry integration publishes CPU, memory, and disk usage to the `InfraOps/Host` namespace.
- Switching to live cloud deployment requires only setting `INFRAOPS_AWS_MODE=live` with standard AWS credentials.
