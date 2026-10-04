# InfraOps Operational Runbook

This runbook documents the standard operating procedures (SOPs) for L1 infrastructure operations engineers.
Each section includes purpose, triggers, impacts, manual CLI command equivalents, escalation thresholds, and closure procedures.

---

## Table of Contents

- [SOP-001: High CPU Utilization Remediation](#sop-001-high-cpu-utilization-remediation)
- [SOP-002: High Memory Utilization Remediation](#sop-002-high-memory-utilization-remediation)
- [SOP-003: Disk Volume Exhaustion Remediation](#sop-003-disk-volume-exhaustion-remediation)
- [SOP-004: Managed Service Outage Remediation](#sop-004-managed-service-outage-remediation)
- [SOP-005: DNS Resolution Failure Remediation](#sop-005-dns-resolution-failure-remediation)
- [SOP-006: Network Dependency Unreachable Remediation](#sop-006-network-dependency-unreachable-remediation)

---

## SOP-001: High CPU Utilization Remediation

### 1. Purpose
Remediate sustained excessive CPU utilization causing system latency or request timeouts on target compute nodes.

### 2. Trigger
Rule `high_cpu` breaches sustained threshold (default 85% CPU for 30s; test mode 22% for 2s).

### 3. Business & Technical Impact
Degraded application response latency, dropped background tasks, and potential host unresponsiveness.

### 4. Pre-checks
Verify that host is accessible and system load average corresponds to core count.

### 5. Manual Command Equivalents
```bash
# Check overall system load and per-core utilization
top -b -n 1 | head -n 20

# List top 10 CPU-consuming processes ordered by percentage
ps aux --sort=-%cpu | head -n 11

# Inspect thread details for the offending process
top -H -p <PID>

# Deprioritize the process to reduce immediate scheduling pressure
renice +10 -p <PID>

# Terminate process gracefully with SIGTERM
kill -15 <PID>

# Verify process termination, force kill with SIGKILL if still executing after 5s
kill -9 <PID>
```

### 6. Decision Points
- If the offending process is a vital kernel thread or database engine, do not kill; escalate immediately.
- If the process is a recognized rogue worker or batch loop, deprioritize and terminate.

### 7. Escalation Criteria
Escalate to L2 Linux Team if CPU remains above 70% after two termination attempts.

### 8. Verification
Execute `uptime` and monitor `top` to verify CPU percent drops below 70% for at least 30 seconds.

### 9. Closure Note Template
`INC-xxx closed: Rogue CPU worker PID <PID> identified and terminated per SOP-001. Host CPU normalized below 15%.`

---

## SOP-002: High Memory Utilization Remediation

### 1. Purpose
Mitigate memory exhaustion conditions before the Linux Out-Of-Memory (OOM) killer indiscriminately terminates services.

### 2. Trigger
Rule `high_memory` breaches threshold (default 90% RAM; test mode 35% for 2s).

### 3. Business & Technical Impact
Severe swap thrashing, sluggish execution, and catastrophic unexpected process termination.

### 4. Pre-checks
Examine available swap and system buffers to ensure memory starvation is genuine.

### 5. Manual Command Equivalents
```bash
# Check memory allocation, buffers, cache, and swap space
free -m

# Inspect top 10 memory-consuming processes by Resident Set Size (RSS)
ps aux --sort=-%mem | head -n 11

# Check for active kernel OOM killer events
dmesg -T | grep -i -E "oom|out of memory" | tail -n 20

# Identify processes consuming significant anonymous memory
cat /proc/<PID>/status | grep -E "VmRSS|VmSwap|VmSize"

# Terminate offending memory-consuming process
kill -15 <PID>
```

### 6. Decision Points
- Confirm whether memory leak is localized to an individual worker or distributed across multiple daemons.
- Verify whether stopping the process impacts persistent state.

### 7. Escalation Criteria
Escalate to L2 Engineering if memory consumption remains elevated or immediately re-accumulates.

### 8. Verification
Run `free -m` and verify total memory utilization drops below the alert threshold.

### 9. Closure Note Template
`INC-xxx closed: Memory leak in worker PID <PID> resolved by termination per SOP-002. Free memory restored to safe baseline.`

---

## SOP-003: Disk Volume Exhaustion Remediation

### 1. Purpose
Clear uncompressed and rotated log files when filesystem utilization approaches capacity.

### 2. Trigger
Rule `disk_full_vol` or `disk_full_root` breaches 90% volume utilization.

### 3. Business & Technical Impact
Failed writes, corrupted SQLite journals, service crashes, and inability to write audit logs.

### 4. Pre-checks
Confirm inode availability alongside block consumption to distinguish block from inode exhaustion.

### 5. Manual Command Equivalents
```bash
# Check filesystem block utilization
df -h

# Check filesystem inode utilization
df -i

# Identify largest directories within the volume
du -sh /var/log/* | sort -hr | head -n 10

# Search for rotated or old log files older than 7 days
find /var/log -type f -name "*.log.*" -mtime +7

# Clean uncompressed rotated logs safely
find /var/log -type f -name "*.log" -size +10M -delete

# Inspect whether open deleted files are holding disk space
lsof +L1
```

### 6. Decision Points
- Never delete active database write-ahead log files or pidfiles.
- Target only rotated files, debug traces, and temporary sandbox payloads.

### 7. Escalation Criteria
Escalate to Infrastructure Storage Team if volume remains above 80% after log purge.

### 8. Verification
Run `df -h` and ensure volume space drops below 70%.

### 9. Closure Note Template
`INC-xxx closed: Stale rotated logs purged per SOP-003. Disk volume capacity reclaimed from 96% down to 22%.`

---

## SOP-004: Managed Service Outage Remediation

### 1. Purpose
Diagnose and restart failed application services exposed on local TCP ports.

### 2. Trigger
Rule `service_down` or `http_down` detects unexpected service death or HTTP 5xx responses.

### 3. Business & Technical Impact
API errors, customer request failures, and dependent pipeline stoppage.

### 4. Pre-checks
Verify whether service failure was triggered by port conflicts, memory limits, or external signal.

### 5. Manual Command Equivalents
```bash
# Check service operational status
systemctl status demo-service || ps aux | grep demo_service

# Inspect recent error logs for stack traces or startup errors
tail -n 50 /var/log/demo-service.log

# Check whether service port is bound by an orphaned process
ss -tulpn | grep 8081

# Restart service cleanly
systemctl restart demo-service

# Probe health endpoint using curl
curl -v --connect-timeout 5 http://127.0.0.1:8081/health
```

### 6. Decision Points
- If the service repeatedly crashes on boot, check recent deployment commits and configuration syntax.
- Verify that dependent database or cache services are healthy before restarting.

### 7. Escalation Criteria
Escalate to Application Engineering if restart fails twice or crashes immediately after health check.

### 8. Verification
Verify service PID is stable and `curl http://127.0.0.1:8081/health` returns HTTP 200.

### 9. Closure Note Template
`INC-xxx closed: Managed service restored per SOP-004. Process restarted cleanly and /health endpoint verified.`

---

## SOP-005: DNS Resolution Failure Remediation

### 1. Purpose
Diagnose and restore domain name resolution when primary DNS resolvers fail or timeout.

### 2. Trigger
Rule `dns_failure` indicates queries to critical services or resolvers exceed latency or fail.

### 3. Business & Technical Impact
Widespread service discovery failure, database connection timeouts, and external API drops.

### 4. Pre-checks
Confirm `/etc/resolv.conf` exists and contains valid nameserver directives.

### 5. Manual Command Equivalents
```bash
# Check configured nameservers and options
cat /etc/resolv.conf

# Perform diagnostic lookup using dig
dig +timeout=2 +tries=2 @127.0.0.1 internal.service

# Test resolver fallback using nslookup
nslookup internal.service 1.1.1.1

# Fallback lookup through system resolver mechanism
getent hosts internal.service

# Remove bad resolver fault override or switch to fallback resolver
rm -f /sandbox/faults/dns_fail
```

### 6. Decision Points
- If local caching daemon is unresponsive, restart the local caching resolver.
- If upstream provider is down, switch primary nameserver to corporate secondary resolver.

### 7. Escalation Criteria
Escalate to Network Operations Team if upstream recursive nameservers fail from multiple availability zones.

### 8. Verification
Run `dig internal.service` and confirm query time is under 50ms with NOERROR status.

### 9. Closure Note Template
`INC-xxx closed: Faulty DNS resolver bypassed per SOP-005. Resolution latency restored to normal range.`

---

## SOP-006: Network Dependency Unreachable Remediation

### 1. Purpose
Restore connectivity to unreachable upstream TCP dependencies and services.

### 2. Trigger
Rule `tcp_unreachable` fires after consecutive failed connection attempts to port 8082.

### 3. Business & Technical Impact
Application dependency failures, message queue backups, and transaction rollbacks.

### 4. Pre-checks
Determine whether the outage is host-local or caused by external routing or firewall rules.

### 5. Manual Command Equivalents
```bash
# Test network layer reachability via ping
ping -c 3 127.0.0.1

# Probe transport layer TCP port accessibility
nc -zv -w 3 127.0.0.1 8082

# Check local listening sockets and TCP connection states
ss -tan | grep 8082

# Trace network route to verify where packets are dropped
traceroute -n -m 5 127.0.0.1

# Restart upstream dependency daemon
python -m infraops.demo.supervisor restart demo-upstream
```

### 6. Decision Points
- If ping succeeds but TCP connection is refused, the port is closed or upstream daemon is dead.
- If ping is dropped, inspect security group rules and routing tables.

### 7. Escalation Criteria
Escalate to Cloud Network Engineering if security group or transit gateway misconfiguration is identified.

### 8. Verification
Verify TCP handshake succeeds on port 8082 with `nc -zv 127.0.0.1 8082`.

### 9. Closure Note Template
`INC-xxx closed: Upstream dependency restarted and verified reachable on port 8082 per SOP-006.`
