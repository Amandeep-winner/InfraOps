# InfraOps — Infrastructure Monitoring & Incident Response Platform
## Autonomous Implementation Spec (for AI agent IDE / CLI)

> **Audience:** an autonomous coding agent (Antigravity CLI or similar).
> **Goal:** build the complete project end to end, with minimal human interaction.
> **Read this whole file before writing any code. Then execute phases in order.**

---

## 0. Operating Rules for the Agent (READ FIRST)

1. **Do not ask the user questions.** If something is ambiguous, pick the default stated in this document. If this document is silent, choose the simplest option that works and append a one-line entry to `docs/DECISIONS.md` (`date | decision | reason`).
2. **Work phase by phase** (Section 12). Do not start phase N+1 until phase N's **Gate** commands pass. If a gate fails, fix it; do not skip it.
3. **Commit after each phase** if git is available: `git commit -m "phase N: <title>"`. Run `git init` in Phase 0.
4. **No real cloud required.** All AWS functionality must work in `mock` mode (using `moto`). A `live` mode must exist behind `INFRAOPS_AWS_MODE=live` but is never required to pass tests.
5. **Safety is mandatory.** Remediation actions may only touch resources inside the **sandbox** (Section 9.3) or processes carrying the sandbox marker. Never kill arbitrary processes, never delete files outside the sandbox directory, never run commands outside the allowlist (Section 7.4). This is non-negotiable and has tests.
6. **Everything must run without root** on a normal Linux box or in Docker. Where root would be needed (systemd, mounting filesystems), use the fallbacks defined here.
7. **Every feature needs a test.** Target: `pytest` passes, coverage ≥ 75 % on `infraops/`.
8. **Finish by satisfying Section 14 (Definition of Done)** and print a short summary of what was built and how to run it.
9. Keep code typed (type hints), documented (docstrings on public functions), and lint-clean (`ruff check .` and `ruff format --check .`).
10. Prefer standard library + the dependencies listed in Section 3. Do not add heavy dependencies (no Kubernetes, no Prometheus server, no React build chain).

---

## 1. Project Summary

**InfraOps** is a self-contained platform that monitors Linux/AWS-style infrastructure (EC2 instances, Docker containers, Linux VMs), detects problems, and handles them as a real **L1 incident-response** function would: **detect → investigate → identify cause → remediate (per SOP) → verify → close**, with a full audit timeline and a dashboard.

It exists to demonstrate practical competence in: Linux administration, networking, AWS fundamentals, monitoring, Python/Bash automation, and SOP/runbook-driven incident response (L1 support).

### 1.1 Architecture

```
                 AWS / Linux Infrastructure
                           │
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
        EC2             Docker           Linux VM
          │                │                │
          └────────────────┼────────────────┘
                           ↓
                 Python / Bash Agents
                           ↓
          ┌─────────────────────────────────┐
          │ CPU | RAM | Disk | Net          │
          │ Processes | Services | Logs     │
          │ DNS | HTTP | Ports | SSH | Perms│
          └────────────────┬────────────────┘
                           ↓  (HTTPS/JSON, API key)
                 Ingest API (FastAPI)
                           ↓
                  Alert Engine (rules.yaml)
                           ↓
                 Incident Manager (INC-xxx)
                           ↓
                       SOP Engine
                           ↓
            ┌──────────────┴──────────────┐
            ↓                             ↓
     Auto Remediation               L1 Manual Mode
     (allowlisted actions)          (guided checklist,
            │                        human approval)
            └──────────────┬──────────────┘
                           ↓
                Verify → Close → Report
                           ↓
        Dashboard  +  S3 report archive  +  CloudWatch metrics
```

### 1.2 Must-demonstrate checklist (each item needs a visible artifact: code + test + doc mention)

| Area | Items |
|---|---|
| **Linux** | Processes, services, filesystems, permissions, SSH, logs |
| **Networking** | TCP/IP, DNS, HTTP/HTTPS, ports, connectivity checks, CIDR/subnetting |
| **AWS** | EC2, VPC, IAM, S3, CloudWatch |
| **Monitoring** | CPU, memory, disk, network, service availability, application logs |
| **Automation** | Python, Bash |
| **Incident response** | 6 SOPs, 6 simulated incidents, full lifecycle, timeline, reports |

`docs/COVERAGE.md` must map each checklist item to the file(s) that implement it (Phase 11).

---

## 2. Repository Layout (create exactly this)

```
infraops/
├── README.md
├── IMPLEMENTATION.md                 # this file (keep it)
├── Makefile
├── pyproject.toml
├── .env.example
├── .gitignore
├── Dockerfile.server
├── Dockerfile.agent
├── docker-compose.yml
├── .github/workflows/ci.yml
├── config/
│   ├── alert_rules.yaml
│   ├── agent.yaml
│   └── server.yaml
├── sops/
│   ├── SOP-001-high-cpu.yaml
│   ├── SOP-002-high-memory.yaml
│   ├── SOP-003-disk-full.yaml
│   ├── SOP-004-service-down.yaml
│   ├── SOP-005-dns-failure.yaml
│   └── SOP-006-network-connectivity.yaml
├── infraops/
│   ├── __init__.py
│   ├── common/
│   │   ├── config.py                 # pydantic-settings + YAML loading
│   │   ├── schemas.py                # shared pydantic models (metrics payloads)
│   │   ├── logging.py
│   │   └── sandbox.py                # sandbox path + marker guard (Section 9.3)
│   ├── agent/
│   │   ├── main.py                   # CLI entry: python -m infraops.agent
│   │   ├── shipper.py                # POST to server, retry + local spool
│   │   ├── scheduler.py
│   │   └── collectors/
│   │       ├── base.py
│   │       ├── cpu.py
│   │       ├── memory.py
│   │       ├── disk.py               # real FS + virtual sandbox volume + inodes
│   │       ├── network.py            # iface counters, errors, connections
│   │       ├── processes.py          # top-N, zombies, process count
│   │       ├── services.py           # systemd or pidfile supervisor
│   │       ├── logs.py               # tail + regex classification
│   │       ├── connectivity.py       # TCP, ICMP/ping, ports
│   │       ├── dns.py                # resolution, latency, resolver health
│   │       ├── http.py               # HTTP/HTTPS status, latency, TLS expiry
│   │       ├── ssh_security.py       # sshd_config audit + failed logins
│   │       └── permissions.py        # critical file permission audit
│   ├── server/
│   │   ├── app.py                    # FastAPI app factory
│   │   ├── db.py                     # SQLAlchemy engine/session (SQLite)
│   │   ├── models.py                 # ORM tables
│   │   ├── security.py               # API key auth
│   │   ├── api/
│   │   │   ├── ingest.py
│   │   │   ├── hosts.py
│   │   │   ├── metrics.py
│   │   │   ├── alerts.py
│   │   │   ├── incidents.py
│   │   │   ├── sops.py
│   │   │   ├── tools.py              # CIDR calculator, DNS/port tools
│   │   │   ├── aws.py
│   │   │   └── health.py
│   │   ├── alerting/
│   │   │   ├── rules.py              # load/validate rules
│   │   │   └── engine.py             # evaluate, dedupe, sustain, flap-guard
│   │   ├── incidents/
│   │   │   ├── service.py            # lifecycle state machine
│   │   │   └── reports.py            # markdown report generator
│   │   ├── sop/
│   │   │   ├── loader.py             # parse + validate SOP YAML
│   │   │   ├── engine.py             # step orchestration
│   │   │   ├── actions.py            # allowlisted action implementations
│   │   │   └── verify.py             # verification predicates
│   │   ├── aws/
│   │   │   ├── client.py             # boto3 factory, mock/live switch
│   │   │   ├── ec2.py
│   │   │   ├── vpc.py
│   │   │   ├── iam.py
│   │   │   ├── s3.py
│   │   │   └── cloudwatch.py
│   │   ├── netutils/
│   │   │   └── cidr.py               # subnetting logic
│   │   └── dashboard/
│   │       ├── routes.py
│   │       ├── templates/            # Jinja2
│   │       └── static/               # vanilla JS + Chart.js (vendored), CSS
│   └── demo/
│       ├── demo_service.py           # the "managed" web service (port 8081)
│       ├── demo_upstream.py          # TCP upstream dependency (port 8082)
│       └── supervisor.py             # pidfile-based service manager
├── scripts/
│   ├── bash/
│   │   ├── sys_snapshot.sh           # uptime, df, free, top, ss, last logins
│   │   ├── check_ports.sh
│   │   ├── check_dns.sh
│   │   ├── disk_report.sh
│   │   ├── log_scan.sh
│   │   ├── ssh_audit.sh
│   │   ├── perm_audit.sh
│   │   └── bootstrap_agent.sh        # installs agent as systemd unit/cron
│   ├── simulate/
│   │   ├── __main__.py               # python -m scripts.simulate <name>
│   │   ├── cpu_hog.py
│   │   ├── mem_hog.py
│   │   ├── disk_fill.py
│   │   ├── service_down.py
│   │   ├── dns_failure.py
│   │   └── net_connectivity.py
│   └── demo_run.py                   # runs all 6 incidents end to end
├── infra/
│   ├── terraform/                    # VPC, subnets, SG, EC2, IAM, S3, CW (not applied)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── iam_policies/
│   │       ├── agent_policy.json
│   │       └── server_policy.json
│   └── systemd/
│       ├── infraops-agent.service
│       └── infraops-server.service
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── sandbox/                          # runtime-created, gitignored
└── docs/
    ├── ARCHITECTURE.md
    ├── RUNBOOK.md
    ├── SOP_AUTHORING.md
    ├── COVERAGE.md
    ├── DECISIONS.md
    ├── INCIDENT_EXAMPLES.md
    ├── NETWORKING_NOTES.md
    └── INTERVIEW_NOTES.md
```

---

## 3. Tech Stack & Dependencies

- **Python 3.11+**
- **Runtime deps:** `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `pydantic>=2`, `pydantic-settings`, `pyyaml`, `psutil`, `httpx`, `dnspython`, `jinja2`, `boto3`, `paramiko`, `python-multipart`, `tenacity`, `rich`, `typer`
- **Dev deps:** `pytest`, `pytest-asyncio`, `pytest-cov`, `moto[ec2,s3,iam,cloudwatch]`, `ruff`, `mypy` (optional), `respx`
- **DB:** SQLite (file `./data/infraops.db`), created automatically.
- **Frontend:** server-rendered Jinja2 + vanilla JS + Chart.js **vendored locally** in `static/vendor/` (download once via `scripts/bash/` or write a `make vendor` target using curl; if the download is blocked, fall back to a minimal canvas line-chart helper written in plain JS — never leave the dashboard dependent on a CDN).
- **Packaging:** `pyproject.toml` with console scripts: `infraops-server`, `infraops-agent`, `infraops-sim`.
- **Containers:** Docker + docker-compose (server, 2 agents, optional localstack not needed).

`Makefile` targets (all required):
`install`, `vendor`, `lint`, `test`, `cov`, `run-server`, `run-agent`, `demo-services`, `simulate NAME=cpu`, `demo` (full e2e), `docker-up`, `docker-down`, `clean`.

---

## 4. Configuration

### 4.1 `.env.example`
```
INFRAOPS_API_KEY=dev-secret-key
INFRAOPS_SERVER_URL=http://localhost:8000
INFRAOPS_DB_URL=sqlite:///./data/infraops.db
INFRAOPS_SANDBOX_DIR=./sandbox
INFRAOPS_AWS_MODE=mock            # mock | live
INFRAOPS_AWS_REGION=ap-south-1
INFRAOPS_AUTO_REMEDIATE=true      # false => SOP runs in L1 manual/approval mode
INFRAOPS_HOST_ID=                 # default: hostname
```

### 4.2 `config/agent.yaml`
```yaml
interval_seconds: 5
top_n_processes: 5
disk:
  paths: ["/"]
  virtual_volumes:
    - name: sandbox-data
      path: ./sandbox/data
      capacity_mb: 100
network:
  ping_targets: ["127.0.0.1"]
  tcp_targets:
    - {name: demo-upstream, host: 127.0.0.1, port: 8082}
  ports_expected_listening: [8000, 8081]
dns:
  names: ["localhost", "example.com"]
  resolvers: ["system"]
  fault_flag: ./sandbox/faults/dns_fail          # see 9.3
http:
  checks:
    - {name: demo-service, url: "http://127.0.0.1:8081/health", expect_status: 200, timeout: 2}
services:
  - {name: demo-service, manager: pidfile, pidfile: ./sandbox/run/demo-service.pid, start_cmd: "python -m infraops.demo.demo_service"}
logs:
  files:
    - {path: ./sandbox/logs/demo-service.log, patterns: {error: "ERROR|Traceback", critical: "CRITICAL|OOM"}}
    - {path: /var/log/auth.log, optional: true}
    - {path: /var/log/syslog, optional: true}
ssh_security:
  sshd_config: /etc/ssh/sshd_config
  auth_log: /var/log/auth.log
  optional: true
permissions:
  audit_paths: ["/etc/passwd", "/etc/shadow", "/etc/ssh/sshd_config", "~/.ssh"]
```
Collectors that depend on missing OS files must degrade gracefully (report `status: "unavailable"`, never crash).

---

## 5. Data Model (SQLAlchemy / SQLite)

| Table | Key columns |
|---|---|
| `hosts` | `id` (str, PK), `hostname`, `ip`, `os`, `kind` (ec2/docker/vm), `last_seen`, `status` (up/stale/down), `tags` (JSON) |
| `metrics` | `id`, `host_id`, `ts`, `name` (e.g. `cpu.percent`), `value` (float), `labels` (JSON) — index on `(host_id, name, ts)` |
| `snapshots` | `id`, `host_id`, `ts`, `kind` (processes/services/ports/ssh/perms/dns/http), `payload` (JSON) |
| `log_events` | `id`, `host_id`, `ts`, `source`, `level`, `message`, `matched_pattern` |
| `alerts` | `id`, `rule_id`, `host_id`, `severity`, `state` (firing/resolved), `first_seen`, `last_seen`, `resolved_at`, `value`, `summary`, `incident_id` (nullable) |
| `incidents` | `id` (`INC-001` format, sequential), `title`, `host_id`, `severity` (P1–P4), `state`, `sop_id`, `opened_at`, `resolved_at`, `closed_at`, `root_cause`, `resolution_summary`, `mode` (auto/manual) |
| `incident_events` | `id`, `incident_id`, `ts`, `phase` (detect/investigate/identify/remediate/verify/close/note), `actor` (system/sop/human), `message`, `data` (JSON) |
| `sop_runs` | `id`, `incident_id`, `sop_id`, `state`, `started_at`, `finished_at`, `step_results` (JSON) |
| `approvals` | `id`, `incident_id`, `step_id`, `state` (pending/approved/rejected), `requested_at`, `decided_at` |

Incident state machine (enforce in `incidents/service.py`; invalid transitions raise):
```
DETECTED → INVESTIGATING → IDENTIFIED → REMEDIATING → VERIFYING → RESOLVED → CLOSED
                                  ↘ (verify fails) → REMEDIATING (retry ≤ 2) → ESCALATED
```
`ESCALATED` = SOP failed; the incident gets an escalation note listing what was tried (this models L1 → L2 handoff).

---

## 6. Agent Specification

`python -m infraops.agent` (also `infraops-agent`):
- Loads `config/agent.yaml` + env.
- Every `interval_seconds` runs all collectors; each returns a list of `Metric(name, value, labels)` and/or a `Snapshot(kind, payload)`.
- Heavy collectors (ssh_security, permissions, processes-detail) run on their own slower cadence (default every 60 s).
- Ships a JSON batch to `POST /api/v1/ingest` with header `X-API-Key`. On failure: exponential backoff (tenacity) and **spool to `./sandbox/spool/*.json`**, flushing when the server returns.
- Registers itself on startup (`POST /api/v1/hosts/register`) and sends a heartbeat metric `agent.up=1`.
- Flags: `--once` (single collection, print JSON, for tests), `--host-id`, `--config`.

### 6.1 Metric names (stable contract)

| Collector | Metrics |
|---|---|
| cpu | `cpu.percent`, `cpu.load1`, `cpu.load5`, `cpu.load15`, `cpu.count` |
| memory | `mem.percent`, `mem.used_mb`, `mem.available_mb`, `swap.percent` |
| disk | `disk.percent{mount}`, `disk.free_mb{mount}`, `disk.inode_percent{mount}`, `disk.vol.percent{name}` (virtual volume), `disk.io_read_bytes`, `disk.io_write_bytes` |
| network | `net.bytes_sent`, `net.bytes_recv`, `net.errin`, `net.errout`, `net.dropin`, `net.dropout`, `net.tcp_established`, `net.tcp_listen` |
| processes | `proc.count`, `proc.zombies` + snapshot `processes` (top-N by CPU and by RSS: pid, name, user, cpu, rss_mb, cmdline, **sandbox_marked** bool) |
| services | `service.up{name}` (1/0) + snapshot `services` |
| connectivity | `conn.tcp_up{name}`, `conn.tcp_latency_ms{name}`, `conn.ping_up{target}`, `conn.ping_ms{target}`, `ports.unexpected_listening`, `ports.expected_missing` |
| dns | `dns.up{name}`, `dns.latency_ms{name}`, `dns.resolver_up{resolver}` |
| http | `http.up{name}`, `http.status{name}`, `http.latency_ms{name}`, `tls.days_to_expiry{name}` (https only) |
| logs | `log.errors_per_min{source}`, `log.critical_count{source}` + `log_events` rows |
| ssh_security | `ssh.failed_logins_5m`, `ssh.root_login_enabled`, `ssh.password_auth_enabled`, snapshot with findings |
| permissions | `perm.violations` + snapshot listing each path, expected vs actual mode/owner |

### 6.2 Linux depth requirements (implementation notes)
- **Processes:** use `psutil`; compute CPU % with a priming call + interval; mark `sandbox_marked` when env var `INFRAOPS_SIM=1` is present in the process environment **or** cmdline contains `--infraops-sim`. Detect zombies.
- **Services:** `manager: systemd` → `systemctl is-active <name>` (if `systemctl` missing, mark unavailable); `manager: pidfile` → read pidfile, check `psutil.pid_exists` and cmdline match. Both implement the same `ServiceManager` interface in `infraops/demo/supervisor.py` (`status/start/stop/restart`).
- **Filesystems:** `psutil.disk_partitions` + `disk_usage`, inode usage via `os.statvfs`, mount options (flag `ro` mounts as a finding), plus **virtual volume** usage = sum of file sizes under `path` ÷ `capacity_mb`.
- **Permissions:** compare actual `stat` mode/owner vs expected map (e.g. `/etc/shadow` ≤ 0640, `~/.ssh` 0700, private keys 0600); report world-writable files in configured dirs.
- **SSH:** parse `sshd_config` for `PermitRootLogin`, `PasswordAuthentication`, `Port`, `PubkeyAuthentication`; count `Failed password` / `Invalid user` lines in `auth_log` within 5 min. Also provide `infraops/agent/collectors/ssh_security.py::remote_probe()` using `paramiko` to run `scripts/bash/sys_snapshot.sh` on a remote host (used by an optional `infraops-agent --ssh user@host` mode; unit-test with a mocked paramiko client).
- **Logs:** incremental tail with stored offsets (handle rotation: inode change/truncate), regex classification, ring-buffer of last 200 events per source.

### 6.3 Networking depth requirements
- **TCP:** `socket.create_connection` with timeout; record latency; distinguish `refused` / `timeout` / `unreachable` in labels.
- **ICMP:** call `ping -c1 -W1`; if `ping` is unavailable, fall back to TCP connect and set label `method=tcp`.
- **DNS:** `dnspython` resolver with explicit timeouts; support `system` resolver and explicit IPs; record A/AAAA answer, TTL, latency.
- **HTTP/HTTPS:** `httpx`; TLS cert expiry via `ssl` + `socket` for https URLs.
- **Ports:** compare `psutil.net_connections(kind="inet")` LISTEN set vs `ports_expected_listening`.
- **CIDR/subnetting:** `infraops/server/netutils/cidr.py` using `ipaddress`: network/broadcast/netmask/wildcard/host range/usable hosts, `contains(ip)`, `split(cidr, new_prefix)`, `overlaps(a,b)`, AWS-aware usable count (AWS reserves 5 addresses per subnet). Exposed via `GET /api/v1/tools/cidr?cidr=10.0.0.0/16&split=24` and in the dashboard "Network Tools" page.

---

## 7. Server Specification

### 7.1 API (all under `/api/v1`, header `X-API-Key` required except `/health` and dashboard HTML)

| Method & path | Purpose |
|---|---|
| `GET /health` | liveness (no auth) |
| `POST /hosts/register` | upsert host |
| `GET /hosts`, `GET /hosts/{id}` | list/detail incl. latest metrics |
| `POST /ingest` | batch of `{host_id, ts, metrics[], snapshots[], log_events[]}` → store → run alert engine |
| `GET /metrics?host_id=&name=&since=&until=&step=` | time series (downsample by `step` seconds) |
| `GET /alerts?state=` | alerts |
| `GET /incidents`, `GET /incidents/{id}` | list/detail with timeline |
| `POST /incidents/{id}/approve/{step_id}` / `reject` | manual-mode approvals |
| `POST /incidents/{id}/note` | human note |
| `POST /incidents/{id}/close` | close a RESOLVED incident |
| `GET /incidents/{id}/report` | markdown report |
| `GET /sops`, `GET /sops/{id}` | SOP library |
| `POST /sops/{id}/run?host_id=` | manual SOP execution |
| `GET /tools/cidr`, `GET /tools/dns?name=`, `GET /tools/port?host=&port=` | NOC utility endpoints |
| `GET /aws/ec2`, `/aws/vpc`, `/aws/iam`, `/aws/s3`, `/aws/cloudwatch` | AWS views (mock or live) |
| `POST /sim/{name}` , `POST /sim/{name}/stop` | trigger/stop simulations from dashboard (only when `INFRAOPS_SANDBOX_DIR` set; uses `scripts/simulate`) |

Return Pydantic-typed JSON. Auto OpenAPI docs at `/docs`.

### 7.2 Alert Engine (`config/alert_rules.yaml`)

Rule format:
```yaml
rules:
  - id: high_cpu
    metric: cpu.percent
    op: ">"
    threshold: 85
    for_seconds: 15          # must hold continuously
    severity: P2
    sop: SOP-001
    summary: "CPU {value:.0f}% on {host_id}"
  - id: high_memory
    metric: mem.percent
    op: ">"
    threshold: 90
    for_seconds: 15
    severity: P2
    sop: SOP-002
  - id: disk_full_vol
    metric: disk.vol.percent
    op: ">="
    threshold: 90
    for_seconds: 5
    severity: P2
    sop: SOP-003
  - id: disk_full_root
    metric: disk.percent
    op: ">="
    threshold: 90
    for_seconds: 30
    severity: P2
    sop: SOP-003
  - id: service_down
    metric: service.up
    op: "=="
    threshold: 0
    for_seconds: 10
    severity: P1
    sop: SOP-004
  - id: dns_failure
    metric: dns.up
    op: "=="
    threshold: 0
    for_seconds: 10
    severity: P2
    sop: SOP-005
  - id: tcp_unreachable
    metric: conn.tcp_up
    op: "=="
    threshold: 0
    for_seconds: 10
    severity: P2
    sop: SOP-006
  - id: http_down
    metric: http.up
    op: "=="
    threshold: 0
    for_seconds: 10
    severity: P1
    sop: SOP-004
  - id: tls_expiring
    metric: tls.days_to_expiry
    op: "<"
    threshold: 14
    for_seconds: 0
    severity: P3
  - id: ssh_bruteforce
    metric: ssh.failed_logins_5m
    op: ">"
    threshold: 20
    for_seconds: 0
    severity: P3
  - id: host_stale
    type: heartbeat
    stale_after_seconds: 30
    severity: P1
  - id: log_error_burst
    metric: log.errors_per_min
    op: ">"
    threshold: 10
    for_seconds: 0
    severity: P3
```
Engine behavior:
- Evaluate on every ingest, keyed by `(rule_id, host_id, labels)`.
- `for_seconds` sustain window; **dedupe** (one open alert per key); **resolve** when condition clears for `resolve_after_seconds` (default 15) — add flap guard.
- A rule with `sop` set **opens an incident** (if none open for same key) and enqueues the SOP run. Rules without `sop` only create alerts.
- Background task (`asyncio`) for heartbeat/stale-host rule every 5 s.

### 7.3 SOP Engine

**SOP file schema** (validate with Pydantic; reject invalid files at startup with a clear error):
```yaml
id: SOP-001
title: High CPU Utilisation
severity_default: P2
trigger: { alert_rule: high_cpu }
owner: L1
estimated_minutes: 5
description: >
  Steps L1 follows when sustained CPU exceeds the threshold.
steps:
  - id: s1
    phase: investigate
    name: Capture system snapshot
    action: collect_snapshot            # allowlisted action name
    params: { include: [processes, load, uptime] }
  - id: s2
    phase: investigate
    name: List top CPU consumers
    action: top_processes
    params: { sort: cpu, limit: 5 }
  - id: s3
    phase: identify
    name: Identify offending process
    action: identify_offender
    params: { metric: cpu, min_percent: 50, require_sandbox_marker: true }
    store_as: offender
  - id: s4
    phase: remediate
    name: Lower priority of offender (renice +10)
    action: renice_process
    params: { pid: "{offender.pid}", niceness: 10 }
    risk: low
  - id: s5
    phase: remediate
    name: Terminate offending process (SIGTERM, then SIGKILL after 5s)
    action: kill_process
    params: { pid: "{offender.pid}", grace_seconds: 5 }
    risk: medium
    requires_approval_in_manual: true
  - id: s6
    phase: verify
    name: Confirm CPU recovered
    action: verify_metric
    params: { metric: cpu.percent, op: "<", threshold: 70, within_seconds: 30, sustain_seconds: 5 }
rollback_note: "Process can be relaunched by owner; no data mutation."
escalation:
  if_failed: "Escalate to L2 Linux team with attached snapshot and process list."
references: ["docs/RUNBOOK.md#sop-001"]
```

**Engine rules (`sop/engine.py`):**
- Executes steps sequentially, grouped by phase; records every step result (`ok`, `output`, `duration_ms`) into `sop_runs.step_results` **and** as `incident_events` (this IS the incident timeline).
- Each phase transition updates the incident state (investigate→INVESTIGATING, identify→IDENTIFIED, remediate→REMEDIATING, verify→VERIFYING).
- **Auto mode** (`INFRAOPS_AUTO_REMEDIATE=true`): runs all steps, except steps with `risk: high` which require approval.
- **Manual / L1 guided mode** (`false`, or per-call): investigation steps run automatically; remediation steps with `requires_approval_in_manual` pause creating an `approvals` row until approved via API/dashboard.
- On verify failure: retry remediation block up to 2 times, then `ESCALATED` with a generated escalation note.
- Template variables `{offender.pid}` resolve from earlier `store_as` outputs; unresolved variables fail the step safely.
- Actions execute **on the target host**. For this project's single-machine/demo deployment the server calls the agent's local action API: each agent exposes `POST /agent/action` on `127.0.0.1:8099` (token-protected by the same API key) and the server dispatches to it. Implement `infraops/agent/action_api.py` (small FastAPI/uvicorn or `http.server`) so the topology stays server→agent. In docker-compose each agent container exposes the port on the compose network.

### 7.4 Allowlisted actions (`sop/actions.py` and agent-side executor)

Only these action names exist; anything else is rejected. **No arbitrary shell.**

| Action | Behavior | Guardrails |
|---|---|---|
| `collect_snapshot` | run `scripts/bash/sys_snapshot.sh`, return text | read-only |
| `top_processes` | psutil top-N | read-only |
| `identify_offender` | pick top process meeting criteria | `require_sandbox_marker` default **true** |
| `renice_process` | `psutil.Process.nice()` | sandbox-marked only |
| `kill_process` | SIGTERM → wait → SIGKILL | sandbox-marked only; never pid ≤ 1, never self/parent |
| `memory_report` | `free -m`, top RSS | read-only |
| `disk_report` | `df -h`, `du` top dirs under allowed path | read-only |
| `find_large_files` | list largest files under sandbox/monitored volume | path must be inside sandbox |
| `clean_path` | delete/compress files matching glob older than N min under volume | path inside sandbox only; dry-run flag; logs bytes freed |
| `service_status` / `service_start` / `service_restart` | via `ServiceManager` | only services declared in `agent.yaml` |
| `check_logs` | last N matching log lines | read-only |
| `dns_diagnose` | resolve via each resolver, report | read-only |
| `dns_switch_resolver` | remove DNS fault flag / set resolver override to fallback | sandbox flag path only |
| `ping_check`, `tcp_check`, `traceroute_lite` | connectivity diagnostics | read-only |
| `restart_dependency` | restart a declared service dependency | declared services only |
| `verify_metric` | wait for metric condition from DB | read-only |
| `verify_http` | GET URL expects status | declared URLs only |
| `verify_service` | service.up == 1 | read-only |
| `notify` | write to incident timeline (+ optional webhook if configured) | – |

Guard layer `infraops/common/sandbox.py`: `assert_in_sandbox(path)` (resolve symlinks, reject `..` escapes) and `assert_sandbox_process(pid)`. **Write unit tests that attempt escapes (path traversal, symlink, pid 1, non-marked process) and assert rejection.**

### 7.5 Incident Reports (`incidents/reports.py`)
On RESOLVED/CLOSED generate `reports/INC-xxx.md` containing: summary, severity, host, timeline table (timestamp, phase, actor, message), root cause, actions taken, verification evidence, SOP used, time-to-detect / time-to-resolve, follow-ups. In mock-AWS mode also `put_object` to the mock S3 bucket `infraops-incident-reports` (`INC-001/report.md`). Serve at `/api/v1/incidents/{id}/report` and dashboard page.

### 7.6 AWS Module (`infraops/server/aws/`)

`client.py`: `get_client(service)` returns a boto3 client. In `mock` mode, start `moto.mock_aws()` at app startup and **seed** the mock account (idempotent) with:
- VPC `10.0.0.0/16` (`infraops-vpc`), 2 public subnets (`10.0.1.0/24`, `10.0.2.0/24`) and 2 private subnets (`10.0.11.0/24`, `10.0.12.0/24`) across 2 AZs, IGW, route tables, security group `infraops-sg` (22 from admin CIDR only, 8000 from VPC, 443 public)
- 3 EC2 instances (`infraops-web-1`, `infraops-web-2`, `infraops-db-1`) with tags
- IAM role `infraops-agent-role` + policies from `infra/terraform/iam_policies/`
- S3 buckets `infraops-incident-reports`, `infraops-log-archive` (versioning on, public access block)
- CloudWatch: agent publishes selected metrics (`InfraOps/Host` namespace: CPUPercent, MemPercent, DiskPercent) via `put_metric_data`; a CloudWatch alarm for each

Endpoints return structured summaries; dashboard "AWS" page shows instances (state, type, AZ, tags), VPC/subnet table with CIDR usable-host counts (reusing `cidr.py`), SG rules with a **risk flag** (e.g. 0.0.0.0/0 on port 22 is flagged), IAM role/policy summary with a **least-privilege check** (flag `"*"` actions/resources), S3 buckets (versioning, public-access-block status), and recent CloudWatch alarm states. `live` mode uses the same code with real credentials (read-only calls only unless explicitly publishing metrics).

### 7.7 Terraform (`infra/terraform/`)
Provide valid, `terraform validate`-clean (don't require running) HCL for: VPC, subnets, route tables, IGW, security groups, EC2 (t3.micro, Amazon Linux 2023 AMI data source, user_data runs `bootstrap_agent.sh`), IAM role + instance profile with least-privilege JSON from `iam_policies/`, S3 buckets (versioning, encryption, public access block), CloudWatch log group + alarms. Include a README block at top of `main.tf` explaining that it is not applied in this project. If `terraform` is installed run `terraform fmt -check` and `terraform validate`; otherwise skip.

---

## 8. Dashboard Specification

Server-rendered pages (Jinja2), dark/light-aware, responsive, no build step. Auto-refresh via `fetch` polling every 5 s.

1. **Overview (`/`)** — host cards (status dot, CPU/MEM/DISK mini gauges), open incident count by severity, open alerts list, last 5 incidents.
2. **Host detail (`/hosts/{id}`)** — time-series charts (CPU, memory, disk incl. virtual volume, network bytes, DNS/HTTP latency), top processes table, services table, ports table, SSH security findings, permission findings, recent log events.
3. **Incidents (`/incidents`)** — filterable table (state, severity, host).
4. **Incident detail (`/incidents/{id}`)** — **visual stepper** `Detect → Investigate → Identify → Remediate → Verify → Close`, live timeline, SOP steps with pass/fail, approval buttons (manual mode), "Download report".
5. **SOP library (`/sops`)** — list + detail view rendering each SOP's steps, risk badges, escalation path.
6. **Simulator (`/simulate`)** — buttons to trigger each of the 6 incidents and a toggle for Auto vs Manual (L1 guided) mode; clear banner "Sandbox only".
7. **Network Tools (`/tools`)** — CIDR calculator (+split), DNS lookup, port checker.
8. **AWS (`/aws`)** — Section 7.6 views.
9. **Audit (`/audit`)** — SSH findings, permission findings, security-group risks, IAM findings in one place.

Design: clean, professional NOC look; severity colors (P1 red, P2 orange, P3 yellow, P4 blue); no emojis required; accessible contrast.

---

## 9. Incident Simulation

### 9.1 Principle
Simulations create **real, observable conditions inside a safe sandbox**, so detection and remediation are genuine rather than faked database rows.

### 9.2 Demo components (`infraops/demo/`)
- `demo_service.py` — tiny HTTP server on `:8081` with `/health` (200), `/work`, writes logs to `sandbox/logs/demo-service.log`, writes pidfile. Cmdline includes `--infraops-sim`.
- `demo_upstream.py` — TCP listener on `:8082` (echo) with same marker; the "dependency" the service/agent checks (network incident).
- `supervisor.py` — `ServiceManager` (pidfile-based start/stop/restart/status, detached background process, log redirection).

### 9.3 Sandbox
`INFRAOPS_SANDBOX_DIR` (default `./sandbox`) with subdirs `data/`, `logs/`, `run/`, `faults/`, `spool/`. All simulations/remediations are confined here (enforced by `common/sandbox.py`).

### 9.4 The six incidents (each: simulator, expected alert, SOP, expected verification)

| # | Name | Simulator behavior (`python -m scripts.simulate <name>` + `--stop`) | Detected by | SOP | Remediation | Verification |
|---|---|---|---|---|---|---|
| INC-001 | High CPU | `cpu_hog.py` spawns N busy-loop workers (N = cpu_count) with marker | `high_cpu` | SOP-001 | renice → kill offender | `cpu.percent < 70` sustained |
| INC-002 | High Memory | `mem_hog.py` allocates memory in steps to a safe cap (min(60% of available, 1.5 GB)) and holds | `high_memory` (use test threshold override via `INFRAOPS_TEST_THRESHOLDS`, see 9.5) | SOP-002 | identify top RSS marked proc → kill | `mem.percent` below threshold |
| INC-003 | Disk Full | `disk_fill.py` writes files into `sandbox/data/` until virtual volume ≥ 95% (100 MB cap), including old-looking `*.log` files | `disk_full_vol` | SOP-003 | disk_report → find_large_files → clean_path (rotated logs/old tmp) | `disk.vol.percent < 70` |
| INC-004 | Service Down | `service_down.py` kills the demo service process | `service_down` + `http_down` | SOP-004 | status → check_logs → restart → verify | `service.up==1`, `/health` 200 |
| INC-005 | DNS Failure | `dns_failure.py` creates `sandbox/faults/dns_fail` making agent's DNS collector use a dead resolver `127.0.0.1:5399` | `dns_failure` | SOP-005 | dns_diagnose → dns_switch_resolver (remove flag/fallback resolver) | `dns.up==1` |
| INC-006 | Network Connectivity | `net_connectivity.py` stops `demo_upstream` | `tcp_unreachable` | SOP-006 | ping_check → tcp_check → traceroute_lite → restart_dependency | `conn.tcp_up==1` |

### 9.5 Test thresholds
For fast demos/tests, support `INFRAOPS_TEST_THRESHOLDS=1` which loads a `config/alert_rules.test.yaml` override (lower thresholds/shorter `for_seconds`). Create that file too. Memory/CPU incidents must also work with the default rules on a typical machine; the test override exists so CI on small runners is deterministic.

### 9.6 SOP content requirements (all six must be fully written)
Each SOP YAML must contain: investigate steps (≥2), identify step, remediate steps (≥1, with risk labels), verify step, escalation text, `rollback_note`. Also write human-readable runbook sections `docs/RUNBOOK.md#sop-00X` with: Purpose, Trigger, Impact, Pre-checks, Manual command equivalents (the real Linux commands an L1 would type: `top`, `ps aux --sort=-%cpu`, `free -m`, `df -h`, `du -sh *`, `lsof`, `systemctl status`, `journalctl -u`, `dig`, `nslookup`, `ss -tulpn`, `ping`, `traceroute`, `curl -v`, `nc -zv`), Decision points, Escalation criteria, Verification, Closure note template.

### 9.7 End-to-end demo script (`scripts/demo_run.py`, `make demo`)
1. Start server (in-process or subprocess), agent, demo service, demo upstream in a temp sandbox with test thresholds.
2. For each incident 001→006: trigger sim → wait for incident → assert lifecycle reached `RESOLVED` within timeout (default 120 s) → print timeline → close incident.
3. Print summary table: incident id, title, MTTD, MTTR, SOP, result.
4. Exit non-zero if any incident failed. Save reports to `./reports/`.

---

## 10. Bash Scripts (all POSIX-friendly, `set -euo pipefail`, `--help`, exit codes documented, shellcheck-clean)

- `sys_snapshot.sh` — hostname, uptime, load, `free -m`, `df -h`, `df -i`, top 10 by CPU and MEM, `ss -s`, listening ports, last logins, failed services (if systemd).
- `check_ports.sh <host> <port...>` — `nc -z` or `/dev/tcp` fallback.
- `check_dns.sh <name> [resolver]` — `dig`/`nslookup`/`getent` fallback chain.
- `disk_report.sh <path>` — usage, top directories by size, largest files.
- `log_scan.sh <file> <regex> [minutes]` — scan recent matching lines with counts.
- `ssh_audit.sh` — sshd_config findings + failed login summary (graceful if files unreadable).
- `perm_audit.sh` — critical file perms + world-writable scan in given dirs.
- `bootstrap_agent.sh` — create venv, install package, write systemd unit or cron fallback; idempotent; supports `--dry-run`.

Python wrappers invoke these via `subprocess` with fixed argv (never string-built shell). Add `tests/unit/test_bash_scripts.py` running them with `--help` and a smoke run where safe.

---

## 11. Docker

- `Dockerfile.server`, `Dockerfile.agent` (python:3.11-slim, non-root user, healthcheck).
- `docker-compose.yml`: services `server` (port 8000, volume for data), `agent-web1`, `agent-web2` (each with its own host id, `kind=docker`, and its own demo service), shared network. Environment from `.env`. Agents' sandbox is a per-container volume.
- `make docker-up` brings the dashboard up with two hosts reporting within 30 s.
- Systemd unit templates in `infra/systemd/` for real Linux/EC2 deployment.

---

## 12. Implementation Phases & Gates

Execute strictly in order. For each phase: implement → write tests → run Gate → commit.

### Phase 0 — Scaffold
Create repo layout, `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`, ruff config, empty packages, `git init`, `docs/DECISIONS.md`. Create venv and install deps.
**Gate:** `python -c "import infraops"`; `make lint` passes; `make test` runs (0 tests OK).

### Phase 1 — Common + Sandbox guard
`config.py`, `schemas.py`, `logging.py`, `sandbox.py` with guard tests (traversal, symlink, pid 1, unmarked process).
**Gate:** `pytest tests/unit/test_sandbox.py` passes.

### Phase 2 — Agent collectors (Linux + Networking)
All collectors in 6.1, graceful degradation, `--once` output, Bash scripts in Section 10.
**Gate:** `python -m infraops.agent --once` prints valid JSON containing cpu, mem, disk, network, processes metrics; unit tests for each collector (mock psutil/sockets where needed); `shellcheck` if installed.

### Phase 3 — Server core (DB, ingest, metrics API)
Models, db init, auth, `/health`, `/hosts`, `/ingest`, `/metrics`, `/hosts/register`; agent `shipper.py` with spool + retry.
**Gate:** integration test: start app via `TestClient`, ingest batch, query series; shipper spools when server down and flushes later.

### Phase 4 — Alert engine
Rules loader/validator, evaluation with sustain/dedupe/resolve/flap guard, heartbeat checker, test override rules.
**Gate:** table-driven unit tests for each rule type (fire, sustain, dedupe, resolve, flap); stale host test.

### Phase 5 — Incident manager + state machine + timeline + reports
Sequential `INC-xxx` ids, valid transitions only, events, markdown report generator.
**Gate:** unit tests for transitions (valid and invalid), id sequencing under concurrency, report content.

### Phase 6 — SOP engine + actions + agent action API
Loader/validator for the six SOPs (write all six fully per 9.6), action implementations with guardrails, approval flow, retry/escalate logic, verification predicates.
**Gate:** unit tests per action (including guardrail rejections); SOP schema validation tests (valid + invalid); engine test with a fake executor covering auto, manual-approval, verify-fail→retry→escalate.

### Phase 7 — Demo components + simulators
`demo_service`, `demo_upstream`, `supervisor`, six simulators with `--stop`, safe resource caps.
**Gate:** each simulator can start/stop in a test without leaving orphan processes (assert after teardown); memory sim never exceeds its cap.

### Phase 8 — End-to-end incidents
Wire everything: agent → ingest → alert → incident → SOP → remediation → verify → resolve. Implement `scripts/demo_run.py`.
**Gate:** `make demo` exits 0 with all six incidents resolved; e2e pytest (`tests/e2e/`, marked `slow`) passes for at least INC-001, INC-003, INC-004 in CI-time budget, others runnable locally.

### Phase 9 — AWS module (mock) + CIDR tools
`client.py` seeding, ec2/vpc/iam/s3/cloudwatch modules, API endpoints, risk checks, agent CloudWatch metric publishing, S3 report upload, CIDR utility + tests, Terraform files.
**Gate:** moto-based tests for each AWS module; CIDR tests (`/16` split into `/24`s, overlap, AWS-usable hosts = 2^n − 5, invalid input handling); `terraform validate` if available.

### Phase 10 — Dashboard
All pages in Section 8, vendored chart lib, polling refresh, incident stepper, simulator controls with Auto/Manual toggle, approvals UI.
**Gate:** `TestClient` GET on every page returns 200 and contains key markers; manual smoke via `make run-server` and `make run-agent` followed by `make simulate NAME=cpu` shows an incident progress in the UI. Capture screenshots into `docs/screenshots/` if a headless browser (e.g. playwright) is available; otherwise skip.

### Phase 11 — Docs, Docker, CI
`README.md` (quickstart, architecture diagram, screenshots, demo GIF optional), `ARCHITECTURE.md`, `RUNBOOK.md` (all 6 SOPs), `SOP_AUTHORING.md`, `INCIDENT_EXAMPLES.md` (real timelines captured from demo run), `NETWORKING_NOTES.md` (TCP/IP, DNS, HTTP/S, ports, CIDR explained as applied in the project), `COVERAGE.md` (checklist → files), `INTERVIEW_NOTES.md` (Section 13). Dockerfiles, compose, GitHub Actions CI (lint, test, build images).
**Gate:** `docker compose config` validates (if docker available); CI YAML parses; all doc links resolve (write a tiny link checker test).

### Phase 12 — Hardening & final verification
Run full suite with coverage, lint, format, a last full `make demo`. Fix flakes (use polling with timeouts, not fixed sleeps). Ensure `make clean` leaves no stray processes or sandbox files. Update `DECISIONS.md`.
**Gate:** Section 14.

---

## 13. `docs/INTERVIEW_NOTES.md` content (write this)

Short, honest notes mapping the project to L1/L2 infrastructure-support work:
- How the project mirrors an L1 incident workflow (detect, triage, follow SOP, remediate, verify, document, escalate).
- A table of "what the interviewer might ask" → "where in the project it is demonstrated" (e.g. *"How do you troubleshoot high CPU on Linux?"* → SOP-001 + `ps`, `top`, `renice`, `kill`; *"Site can't resolve names"* → SOP-005 + `dig`/resolver checks; *"What's /24 and how many hosts?"* → CIDR tool and AWS reserved 5 addresses; *"EC2 instance unreachable?"* → SG/NACL/route/IGW checks in AWS view, SOP-006).
- Limits/assumptions (mock AWS, sandboxed remediation) stated plainly.
- A 60-second and a 3-minute verbal walkthrough script.

---

## 14. Definition of Done (all must be true)

- [ ] `make install && make lint && make test` pass; coverage ≥ 75 %.
- [ ] `make demo` resolves INC-001 … INC-006 end to end, prints the summary table, and writes six reports to `./reports/`.
- [ ] Dashboard shows hosts, charts, incidents with stepper/timeline, SOP library, simulator, network tools, AWS, audit pages.
- [ ] Manual (L1 guided) mode works: remediation pauses for approval and proceeds after approving in the UI/API.
- [ ] Verify-failure path demonstrably retries then escalates (covered by a test).
- [ ] All six SOPs exist as YAML **and** as runbook sections with manual command equivalents.
- [ ] Guardrail tests prove remediation cannot touch non-sandbox paths/processes or run non-allowlisted commands.
- [ ] Mock-AWS mode shows EC2, VPC/subnets (with CIDR math), IAM findings, S3 buckets (reports uploaded), CloudWatch metrics/alarms; Terraform files present.
- [ ] Bash scripts present, executable, `--help` works, shellcheck-clean if available.
- [ ] Docker compose defines server + 2 agents; images build if Docker is available.
- [ ] All docs in Section 2 exist, README quickstart works from a clean clone in ≤ 5 commands.
- [ ] No secrets committed; `.env.example` only; API key required on all non-public endpoints.
- [ ] No orphan processes or leftover sandbox state after tests/demo.

---

## 15. Quickstart (README must reproduce this and it must work)

```bash
git clone <repo> && cd infraops
make install
cp .env.example .env
make run-server            # terminal 1  → http://localhost:8000
make run-agent             # terminal 2  (also starts demo services)
make simulate NAME=cpu     # terminal 3  → watch INC-001 on the dashboard
make demo                  # runs all six incidents unattended
```

---

## 16. Troubleshooting Guidance for the Agent

- **psutil CPU reads 0 on first call:** prime with `psutil.cpu_percent(None)` then sample after the interval.
- **ping missing/blocked in containers:** use the TCP fallback (6.3), mark `method=tcp`.
- **systemctl missing:** use the pidfile supervisor; never fail the collector.
- **moto + boto3 region errors:** always pass `region_name` and dummy credentials (`AWS_ACCESS_KEY_ID=testing`) in mock mode.
- **Flaky timing tests:** replace sleeps with a `wait_until(predicate, timeout, interval)` helper in `tests/conftest.py`.
- **SQLite locking under concurrent ingest:** enable WAL (`PRAGMA journal_mode=WAL`), short transactions, a single writer lock around incident creation.
- **Port conflicts in tests:** bind ephemeral ports (`port=0`) and pass the discovered port through config.
- **Chart library download blocked:** use the built-in minimal canvas chart helper (Section 3).
- **If a gate cannot be satisfied because of the environment** (e.g. no Docker): log the reason in `docs/DECISIONS.md`, skip only that sub-check, and continue.

---

## 17. Final Output Expected from the Agent

When finished, print:
1. A tree of the created project (depth 2).
2. Results of `make lint`, `make test` (with coverage %), and `make demo` summary table.
3. The exact commands to start the dashboard.
4. A short list of any skipped checks with reasons (from `DECISIONS.md`).
