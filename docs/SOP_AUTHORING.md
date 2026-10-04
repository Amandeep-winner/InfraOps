# SOP Authoring Guide

This guide describes how to author, test, and validate declarative Standard Operating Procedures (SOPs) for the InfraOps incident response engine.

---

## 1. SOP Specification Schema

Every SOP is defined as a YAML file located in the `sops/` directory.
File names follow the convention: `SOP-XXX-descriptive-name.yaml`.

```yaml
id: "SOP-001"
title: "High CPU Utilization Remediation"
description: >
  Operational workflow executed when sustained host CPU breaches defined thresholds.
trigger_rules:
  - "high_cpu"
steps:
  - id: "s1"
    phase: "investigate"
    name: "Capture system snapshot"
    action: "collect_snapshot"
    params:
      include: ["processes", "load", "uptime"]

  - id: "s2"
    phase: "identify"
    name: "Identify offending process"
    action: "identify_offender"
    params:
      metric: "cpu"
      min_percent: 20
      require_sandbox_marker: true
    store_as: "offender"

  - id: "s3"
    phase: "remediate"
    name: "Terminate offending rogue process"
    action: "kill_process"
    params:
      pid: "{offender.pid}"
      grace_seconds: 5
    risk: "medium"
    requires_approval_in_manual: true

  - id: "s4"
    phase: "verify"
    name: "Confirm CPU utilization normalized"
    action: "verify_metric"
    params:
      metric: "cpu.percent"
      op: "<"
      threshold: 70
      within_seconds: 30
      sustain_seconds: 2

rollback_note: "Terminated rogue process can be relaunched by service owner."
escalation:
  if_failed: "Escalate to L2 Linux engineering team with attached diagnostics."
references:
  - "docs/RUNBOOK.md#sop-001-high-cpu-utilization-remediation"
```

---

## 2. Step Fields & Semantics

### `id`
A unique string identifier within the SOP (e.g. `s1`, `s2`, `s3`).

### `phase`
The operational incident lifecycle phase.
Allowed values:
- `investigate`: Collect system state, logs, and diagnostic dumps.
- `identify`: Pinpoint offending PIDs, anomalous files, or broken sockets.
- `remediate`: Execute state-altering corrective operations.
- `verify`: Validate that target metrics or service checks have recovered.

### `action`
Must strictly reference an allowlisted action from `infraops/server/sop/actions.py`.
Arbitrary shell commands are unconditionally rejected.

### `params`
Key-value mapping providing parameters required by the allowlisted action.
Parameters support template variable interpolation.

### `store_as`
Optional string identifier under which the step output dictionary is stored.
Subsequent steps can reference stored fields using curly braces (e.g. `{offender.pid}`).

### `risk`
Risk classification for the remediation action: `low`, `medium`, or `high`.
- In Auto Mode, `low` and `medium` steps execute automatically, while `high` risk steps pause for operator approval.
- In Manual (L1 Guided) Mode, any step marked with `requires_approval_in_manual: true` pauses execution until approved.

---

## 3. Allowlisted Actions Reference

| Action Name | Description | Key Parameters |
|---|---|---|
| `collect_snapshot` | Executes `sys_snapshot.sh` to capture system baseline. | `include` (list) |
| `top_processes` | Queries top N processes by CPU or memory. | `sort`, `limit` |
| `identify_offender` | Selects the top process breaching a resource threshold. | `metric`, `min_percent`, `require_sandbox_marker` |
| `renice_process` | Adjusts scheduling priority of a target process. | `pid`, `niceness` |
| `kill_process` | Sends SIGTERM followed by SIGKILL to sandbox process. | `pid`, `grace_seconds` |
| `disk_report` | Executes `disk_report.sh` across virtual volume. | `path` |
| `find_large_files` | Locates largest files within sandbox directory. | `path`, `limit` |
| `clean_path` | Deletes or archives files matching a glob pattern. | `path`, `glob`, `older_than_minutes`, `dry_run` |
| `service_status` | Queries operational state of managed service. | `service` |
| `service_start` | Starts a declared service. | `service` |
| `service_restart` | Restarts a declared service. | `service` |
| `check_logs` | Scans recent log lines matching regular expressions. | `path`, `regex`, `lines` |
| `dns_diagnose` | Resolves target hostname across configured nameservers. | `name` |
| `dns_switch_resolver` | Removes dead resolver fault flag or sets fallback. | `resolver` |
| `ping_check` | Sends ICMP ping probes with TCP fallback. | `host`, `count` |
| `tcp_check` | Probes TCP port connectivity. | `host`, `port`, `timeout` |
| `traceroute_lite` | Diagnoses routing hop latency. | `host`, `max_hops` |
| `restart_dependency` | Restarts an upstream managed service dependency. | `service` |
| `verify_metric` | Polls telemetry store for metric recovery predicate. | `metric`, `op`, `threshold`, `within_seconds` |
| `verify_http` | Probes HTTP endpoint expecting designated status code. | `url`, `status_code`, `timeout` |
| `verify_service` | Verifies managed service PID is running. | `service` |
| `notify` | Logs milestone to incident audit timeline. | `channel`, `message` |

---

## 4. Testing & Verifying SOPs

Before deploying a newly authored SOP to production:
1. Run the validator test suite: `pytest tests/unit/test_sop_loader.py`.
2. Execute a simulated run in a mock environment using `tests/unit/test_sop_engine.py`.
3. Verify that all parameter references resolve correctly without missing key errors.
