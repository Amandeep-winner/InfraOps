# L1 / L2 Infrastructure Operations Interview Reference Notes

These notes provide concise, practical guidance on discussing the InfraOps platform during engineering interviews for infrastructure, DevOps, SRE, and NOC roles.

---

## 1. How InfraOps Mirrors Real-World L1 Incident Response

In modern cloud and enterprise operations, Level-1 (L1) incident response follows a structured, auditable workflow:
1. **Detect**: Continuous telemetry triggers an alert rule with sustained breach thresholds (`for_seconds`) to avoid false alarms from transient spikes.
2. **Triage & Correlate**: Incidents are assigned sequential identifiers (`INC-xxx`) and correlated to specific hosts, preventing duplicate tickets.
3. **Follow Standard Operating Procedures (SOPs)**: Engineers execute runbooks that progress sequentially through diagnostic phases: capture system state, identify root cause, and apply scoped remediation.
4. **Remediate under Least-Privilege**: Remediation uses allowlisted, safe actions without running arbitrary, unvetted shell scripts.
5. **Verify**: Before resolving an incident, the system polls metrics or probes endpoints to confirm stability.
6. **Document & Post-Mortem**: A detailed timeline with timestamps, actors, and findings is committed to persistent storage and S3.
7. **Escalate**: If verification fails or remediation exceeds retry thresholds, the incident escalates to L2 engineering with complete diagnostic state attached.

---

## 2. Common Interview Questions & Project Evidence Mapping

| Interviewer Question | Demonstration in InfraOps | Practical Technical Answer |
|---|---|---|
| **"How do you troubleshoot high CPU on Linux?"** | `sops/SOP-001-high-cpu.yaml`<br>`scripts/bash/sys_snapshot.sh`<br>`infraops/server/sop/actions.py` | Run `top -b -n 1` and `ps aux --sort=-%cpu` to identify rogue processes. Inspect thread counts and system load versus core count. Deprioritize with `renice +10` before terminating with `kill -15` (SIGTERM). |
| **"How do you troubleshoot memory leaks or OOM issues?"** | `sops/SOP-002-high-memory.yaml`<br>`infraops/agent/collectors/memory.py` | Check `free -m` to distinguish buffer/cache from anonymous memory. Inspect `/proc/<PID>/status` for Resident Set Size (VmRSS). Check `dmesg -T` for kernel OOM-killer invocations. |
| **"A disk volume is at 100%. What are your first steps?"** | `sops/SOP-003-disk-full.yaml`<br>`scripts/bash/disk_report.sh` | Run `df -h` for blocks and `df -i` for inodes. Run `du -sh *` to locate ballooning directories. Check `lsof +L1` for open file handles holding deleted files. Purge rotated `.log` archives. |
| **"A service is throwing 502/503 errors or is down. How do you respond?"** | `sops/SOP-004-service-down.yaml`<br>`infraops/demo/supervisor.py` | Inspect `systemctl status` and recent journal logs with `journalctl -u`. Check whether the port is listening using `ss -tulpn`. Check PID files for stale locks, restart cleanly, and verify `/health`. |
| **"The application cannot resolve external or internal hostnames. How do you debug?"** | `sops/SOP-005-dns-failure.yaml`<br>`scripts/bash/check_dns.sh` | Verify `/etc/resolv.conf` nameservers. Probe nameservers with `dig +timeout=2 @<server> <fqdn>`. Test fallback resolution with `nslookup` or `getent hosts`. Swap to secondary resolver if primary times out. |
| **"What is a /24 subnet, and how many usable hosts are there in AWS?"** | `infraops/server/netutils/cidr.py`<br>`infraops/server/aws/vpc.py` | A `/24` prefix allocates 24 network bits and 8 host bits (256 addresses). In standard networking, 254 are usable (subtracting network .0 and broadcast .255). In AWS VPCs, only 251 are usable because AWS reserves 5 addresses (.0 network, .1 VPC router, .2 Amazon DNS, .3 future use, and broadcast). |
| **"An EC2 instance is unreachable over SSH. What do you check?"** | `infraops/server/aws/vpc.py`<br>`infraops/server/aws/iam.py` | Check security group ingress rules (is port 22 open from source CIDR?). Check VPC route table for default route `0.0.0.0/0` targeting Internet Gateway. Check Network ACLs. Inspect instance console screenshot/logs via AWS CLI. |
| **"What constitutes least-privilege in AWS IAM?"** | `infraops/server/aws/iam.py`<br>`infra/terraform/iam_policies/` | Never allow `Action: "*"` or `Resource: "*"` on credentials without tight conditions. Scope actions strictly to resource ARNs. Audit policies programmatically to flag wildcard administrative access. |

---

## 3. Assumptions & Guardrail Boundaries

- **Mock Cloud Environment**: All AWS capabilities execute against Moto by default, enabling full offline testing with zero live cloud costs.
- **Sandboxed Operations**: Process termination and filesystem deletions are strictly confined to `sandbox/` and processes bearing explicit sandbox markers.
- **Rootless Compatibility**: The system runs entirely without root privileges on commodity Linux, Docker, or Windows developer workstations.

---

## 4. Verbal Walkthrough Scripts

### 60-Second Elevator Pitch
"I built InfraOps, a self-contained infrastructure monitoring and Level-1 incident response platform designed to demonstrate real-world systems, networking, and cloud operational skills.
It features a Python and POSIX Bash telemetry agent that monitors 12 distinct system dimensions across Linux and AWS environments.
When telemetry breaches sustained thresholds, a centralized FastAPI alert engine creates a tracked incident ticket with a strict state machine.
The platform executes declarative SOP runbooks that capture diagnostic snapshots, identify root causes, execute allowlisted safe remediations, verify metric normalization, and archive post-mortem reports to S3.
It includes an interactive server-rendered NOC dashboard with visual incident steppers, network CIDR calculators, and cloud security auditors."

### 3-Minute Deep Dive Walkthrough
"InfraOps was engineered from the ground up to reflect production infrastructure support environments.
At the edge, we have an agent that collects metrics for CPU, memory, disk volumes, network sockets, system services, DNS resolution, and log files.
Rather than using heavy runtime frameworks, the agent uses standard Python and POSIX Bash scripts like `sys_snapshot.sh` and `check_ports.sh`.
Metric batches are transmitted to a central FastAPI service backed by an asynchronous SQLite database operating in Write-Ahead Logging mode.
The alert engine implements time-window sustain logic and flapping guards, ensuring alerts only fire when a condition persists across consecutive evaluation periods.
Once triggered, the engine spawns an incident with a unique, sequentially generated ID and transitions through a rigorous state machine: Detect, Investigate, Identify, Remediate, Verify, and Close.
Remediation actions are strictly allowlisted; there is no execution of arbitrary shell strings.
All process terminations require valid sandbox process markers, and all filesystem operations enforce path canonicalization to prevent directory traversal.
The platform supports both autonomous remediation and an L1 guided manual mode where dangerous operations pause for human approval on the dashboard.
Finally, InfraOps models an enterprise AWS topology including VPC subnets, security groups, IAM least-privilege auditing, S3 incident post-mortem archival, and CloudWatch metrics.
The entire platform is verifiable end-to-end through automated incident simulations and comprehensive test suites running completely offline."
