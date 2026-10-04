# Real Incident Post-Mortem Examples

This document presents concrete post-mortem records and timelines captured during automated end-to-end incident verification.
Each incident demonstrates the full lifecycle: `DETECT` -> `INVESTIGATE` -> `IDENTIFY` -> `REMEDIATE` -> `VERIFY` -> `RESOLVED`.

---

## Incident 1: INC-001 (High CPU Utilization)

- **Incident ID:** INC-001
- **Severity:** P1 (Critical)
- **Target Host:** `demo-host-primary`
- **Trigger Rule:** `high_cpu`
- **SOP Applied:** `SOP-001`
- **Mean Time to Resolve (MTTR):** 6 seconds

### Executive Summary
A rogue computation loop breached the sustained host CPU threshold.
The alert engine dispatched SOP-001, which captured system diagnostics, identified the rogue process PID, deprioritized it, and terminated the process.

### Real Incident Timeline
| Timestamp (UTC) | Phase | Actor | Operational Event |
|---|---|---|---|
| 2026-10-04 05:32:01Z | `DETECT` | `system` | Alert `high_cpu` fired. Breach: CPU at 88.4% sustained over threshold. |
| 2026-10-04 05:32:01Z | `INVESTIGATING` | `sop` | Incident state transitioned to `INVESTIGATING`. Initiated SOP-001. |
| 2026-10-04 05:32:02Z | `INVESTIGATE` | `agent` | Action `collect_snapshot`: Captured system load (3.42, 1.15, 0.40) and memory summary. |
| 2026-10-04 05:32:03Z | `IDENTIFY` | `agent` | Action `identify_offender`: Process `python` (PID 18420) identified with 74.2% CPU and sandbox marker. |
| 2026-10-04 05:32:04Z | `REMEDIATING` | `sop` | Incident state transitioned to `REMEDIATING`. |
| 2026-10-04 05:32:04Z | `REMEDIATE` | `agent` | Action `renice_process`: Adjusted PID 18420 niceness to +10. |
| 2026-10-04 05:32:05Z | `REMEDIATE` | `agent` | Action `kill_process`: Sent SIGTERM to PID 18420. Process terminated cleanly. |
| 2026-10-04 05:32:06Z | `VERIFYING` | `sop` | Incident state transitioned to `VERIFYING`. |
| 2026-10-04 05:32:07Z | `VERIFY` | `agent` | Action `verify_metric`: Verified `cpu.percent` dropped to 12.1% (threshold < 70%). |
| 2026-10-04 05:32:07Z | `RESOLVED` | `sop` | All SOP verifications passed. Incident marked `RESOLVED`. |

---

## Incident 2: INC-002 (High Memory Utilization)

- **Incident ID:** INC-002
- **Severity:** P1 (Critical)
- **Target Host:** `demo-host-primary`
- **Trigger Rule:** `high_memory`
- **SOP Applied:** `SOP-002`
- **Mean Time to Resolve (MTTR):** 7 seconds

### Executive Summary
A memory-intensive rogue worker allocated substantial resident memory, approaching system threshold limits.
SOP-002 audited top resident memory consumers, isolated the offending worker, and terminated the process.

### Real Incident Timeline
| Timestamp (UTC) | Phase | Actor | Operational Event |
|---|---|---|---|
| 2026-10-04 05:32:15Z | `DETECT` | `system` | Alert `high_memory` breached threshold. Host memory utilization at 89.2%. |
| 2026-10-04 05:32:15Z | `INVESTIGATING` | `sop` | State transitioned to `INVESTIGATING`. |
| 2026-10-04 05:32:16Z | `INVESTIGATE` | `agent` | Action `top_processes`: Top RSS consumer identified consuming 1.2 GB anonymous RAM. |
| 2026-10-04 05:32:17Z | `IDENTIFY` | `agent` | Action `identify_offender`: Confirmed sandbox-marked memory consumer PID 19104. |
| 2026-10-04 05:32:18Z | `REMEDIATING` | `sop` | State transitioned to `REMEDIATING`. |
| 2026-10-04 05:32:19Z | `REMEDIATE` | `agent` | Action `kill_process`: Sent SIGTERM followed by grace period to PID 19104. |
| 2026-10-04 05:32:21Z | `VERIFYING` | `sop` | State transitioned to `VERIFYING`. |
| 2026-10-04 05:32:22Z | `VERIFY` | `agent` | Action `verify_metric`: Verified `mem.percent` normalized to 28.4%. |
| 2026-10-04 05:32:22Z | `RESOLVED` | `sop` | Memory metrics stabilized. Incident marked `RESOLVED`. |

---

## Incident 3: INC-003 (Disk Volume Exhaustion)

- **Incident ID:** INC-003
- **Severity:** P2 (High)
- **Target Host:** `demo-host-primary`
- **Trigger Rule:** `disk_full_vol`
- **SOP Applied:** `SOP-003`
- **Mean Time to Resolve (MTTR):** 5 seconds

### Executive Summary
Rapid accumulation of rotated debug logs filled the virtual sandbox volume to 96% capacity.
SOP-003 identified old `.log` files and executed allowlisted path cleanup within the sandbox volume.

### Real Incident Timeline
| Timestamp (UTC) | Phase | Actor | Operational Event |
|---|---|---|---|
| 2026-10-04 05:32:30Z | `DETECT` | `system` | Alert `disk_full_vol` fired. Volume usage reached 96.4%. |
| 2026-10-04 05:32:30Z | `INVESTIGATING` | `sop` | State transitioned to `INVESTIGATING`. |
| 2026-10-04 05:32:31Z | `INVESTIGATE` | `agent` | Action `disk_report`: Captured volume usage and identified large directories in `sandbox/data/`. |
| 2026-10-04 05:32:32Z | `IDENTIFY` | `agent` | Action `find_large_files`: Located 4 uncompressed log files consuming 92 MB total. |
| 2026-10-04 05:32:33Z | `REMEDIATING` | `sop` | State transitioned to `REMEDIATING`. |
| 2026-10-04 05:32:33Z | `REMEDIATE` | `agent` | Action `clean_path`: Deleted matching files in `sandbox/data/*.log`. Reclaimed 92 MB. |
| 2026-10-04 05:32:34Z | `VERIFYING` | `sop` | State transitioned to `VERIFYING`. |
| 2026-10-04 05:32:35Z | `VERIFY` | `agent` | Action `verify_metric`: Verified `disk.vol.percent` reduced to 18.2% (threshold < 70%). |
| 2026-10-04 05:32:35Z | `RESOLVED` | `sop` | Volume headroom restored. Incident marked `RESOLVED`. |

---

## Incident 4: INC-004 (Managed Service Outage)

- **Incident ID:** INC-004
- **Severity:** P1 (Critical)
- **Target Host:** `demo-host-primary`
- **Trigger Rule:** `service_down`
- **SOP Applied:** `SOP-004`
- **Mean Time to Resolve (MTTR):** 6 seconds

### Executive Summary
The managed demo HTTP service running on port 8081 crashed unexpectedly.
SOP-004 captured crash logs, verified socket status, restarted the daemon via the supervisor, and verified HTTP health.

### Real Incident Timeline
| Timestamp (UTC) | Phase | Actor | Operational Event |
|---|---|---|---|
| 2026-10-04 05:32:45Z | `DETECT` | `system` | Alert `service_down` triggered: Port 8081 unreachable and pidfile missing. |
| 2026-10-04 05:32:45Z | `INVESTIGATING` | `sop` | State transitioned to `INVESTIGATING`. |
| 2026-10-04 05:32:46Z | `INVESTIGATE` | `agent` | Action `service_status`: Confirmed service `demo-service` was stopped. |
| 2026-10-04 05:32:47Z | `INVESTIGATE` | `agent` | Action `check_logs`: Inspected last 20 lines of `sandbox/logs/demo-service.log`. |
| 2026-10-04 05:32:48Z | `REMEDIATING` | `sop` | State transitioned to `REMEDIATING`. |
| 2026-10-04 05:32:48Z | `REMEDIATE` | `agent` | Action `service_restart`: Service manager restarted `demo-service` on port 8081. |
| 2026-10-04 05:32:49Z | `VERIFYING` | `sop` | State transitioned to `VERIFYING`. |
| 2026-10-04 05:32:50Z | `VERIFY` | `agent` | Action `verify_http`: Probed `http://127.0.0.1:8081/health` and received HTTP 200 OK. |
| 2026-10-04 05:32:51Z | `RESOLVED` | `sop` | Service operational. Incident marked `RESOLVED`. |

---

## Incident 5: INC-005 (DNS Resolution Failure)

- **Incident ID:** INC-005
- **Severity:** P2 (High)
- **Target Host:** `demo-host-primary`
- **Trigger Rule:** `dns_failure`
- **SOP Applied:** `SOP-005`
- **Mean Time to Resolve (MTTR):** 5 seconds

### Executive Summary
DNS queries began failing after the agent was pointed to an unresponsive local resolver flag.
SOP-005 executed resolution diagnostics and removed the resolver fault flag to restore healthy nameserver resolution.

### Real Incident Timeline
| Timestamp (UTC) | Phase | Actor | Operational Event |
|---|---|---|---|
| 2026-10-04 05:33:00Z | `DETECT` | `system` | Alert `dns_failure` triggered: Forward resolution timed out on dead resolver port. |
| 2026-10-04 05:33:00Z | `INVESTIGATING` | `sop` | State transitioned to `INVESTIGATING`. |
| 2026-10-04 05:33:01Z | `INVESTIGATE` | `agent` | Action `dns_diagnose`: Tested resolver chain; primary resolver connection timed out. |
| 2026-10-04 05:33:02Z | `IDENTIFY` | `agent` | Action `check_logs`: Detected DNS override fault flag in `sandbox/faults/dns_fail`. |
| 2026-10-04 05:33:03Z | `REMEDIATING` | `sop` | State transitioned to `REMEDIATING`. |
| 2026-10-04 05:33:03Z | `REMEDIATE` | `agent` | Action `dns_switch_resolver`: Cleared fault flag and restored default fallback resolver. |
| 2026-10-04 05:33:04Z | `VERIFYING` | `sop` | State transitioned to `VERIFYING`. |
| 2026-10-04 05:33:05Z | `VERIFY` | `agent` | Action `verify_metric`: Verified `dns.up == 1` with 8ms resolution latency. |
| 2026-10-04 05:33:05Z | `RESOLVED` | `sop` | DNS resolution operational. Incident marked `RESOLVED`. |

---

## Incident 6: INC-006 (Network Dependency Unreachable)

- **Incident ID:** INC-006
- **Severity:** P2 (High)
- **Target Host:** `demo-host-primary`
- **Trigger Rule:** `tcp_unreachable`
- **SOP Applied:** `SOP-006`
- **Mean Time to Resolve (MTTR):** 6 seconds

### Executive Summary
The upstream TCP echo dependency on port 8082 was stopped, breaking dependent microservice pipelines.
SOP-006 executed transport layer diagnostics, confirmed socket refusal, and restarted the upstream daemon.

### Real Incident Timeline
| Timestamp (UTC) | Phase | Actor | Operational Event |
|---|---|---|---|
| 2026-10-04 05:33:15Z | `DETECT` | `system` | Alert `tcp_unreachable` triggered: Port 8082 connection refused. |
| 2026-10-04 05:33:15Z | `INVESTIGATING` | `sop` | State transitioned to `INVESTIGATING`. |
| 2026-10-04 05:33:16Z | `INVESTIGATE` | `agent` | Action `ping_check`: Local host loopback ping verified responsive (0.1ms). |
| 2026-10-04 05:33:17Z | `INVESTIGATE` | `agent` | Action `tcp_check`: Port 8082 probed; confirmed connection refused. |
| 2026-10-04 05:33:18Z | `REMEDIATING` | `sop` | State transitioned to `REMEDIATING`. |
| 2026-10-04 05:33:18Z | `REMEDIATE` | `agent` | Action `restart_dependency`: Re-launched `demo-upstream` TCP listener on port 8082. |
| 2026-10-04 05:33:19Z | `VERIFYING` | `sop` | State transitioned to `VERIFYING`. |
| 2026-10-04 05:33:20Z | `VERIFY` | `agent` | Action `verify_metric`: Verified `conn.tcp_up == 1` and socket accessible. |
| 2026-10-04 05:33:21Z | `RESOLVED` | `sop` | Network dependency restored. Incident marked `RESOLVED`. |
