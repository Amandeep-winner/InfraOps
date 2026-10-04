# InfraOps - Infrastructure Monitoring & Autonomous L1 Incident Response Platform

InfraOps is a self-contained infrastructure monitoring and Level-1 (L1) incident response platform.
It monitors Linux and AWS-style compute environments, detects system and network anomalies, and handles incidents through a complete operational lifecycle:
**Detect -> Investigate -> Identify Cause -> Remediate (per SOP) -> Verify -> Close**.

---

## Architecture Overview

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

## Key Capabilities

- **Multi-Dimensional Telemetry Collectors**: Continuous monitoring across 12 distinct collector categories (CPU, RAM, Virtual Disks, Network I/O, Processes, Services, Logs, DNS, HTTP, Port connectivity, SSH configuration hardening, and Filesystem permissions).
- **POSIX Shell Diagnostics**: 8 POSIX-compliant, `set -euo pipefail` Bash diagnostic utilities (`sys_snapshot.sh`, `check_ports.sh`, `check_dns.sh`, `disk_report.sh`, `log_scan.sh`, `ssh_audit.sh`, `perm_audit.sh`, `bootstrap_agent.sh`).
- **Declarative SOP Engine**: 6 automated standard operating procedure runbooks defined in YAML with allowlisted, sandboxed actions and verification predicates.
- **Defense-in-Depth Safety Guardrails**: Path canonicalization, symlink escape rejection, PID 1 immunity, self-termination protection, and process marker verification.
- **Server-Rendered NOC Operations Dashboard**: Zero-build Jinja2 dashboard featuring interactive visual incident steppers, canvas time-series charts, live telemetry, simulator controls, CIDR subnet calculators, and security compliance audit views.
- **Mock & Live AWS Topology**: Complete offline-testable cloud environment with VPC subnets (AWS 5-reserved-IP math), Security Groups with 0.0.0.0/0 exposure audits, IAM least-privilege analyzers, S3 report archival, and CloudWatch metric alarms.

---

## Quickstart

Clone the repository and launch the platform with standard make commands:

```bash
git clone https://github.com/Amandeep-winner/InfraOps.git && cd InfraOps
make install
cp .env.example .env
make run-server            # Terminal 1: Starts central NOC API & dashboard on http://localhost:8000
make run-agent             # Terminal 2: Starts telemetry agent and background services
make simulate NAME=cpu     # Terminal 3: Injects safe fault; observe INC-001 on the dashboard
make demo                  # Runs all six incidents end-to-end with automated resolution
```

---

## Operational Workflows & The 6 Incidents

InfraOps provides automated simulators and matching SOP runbooks for the 6 core operational incident categories:

| Incident ID | Incident Name | Simulator Command | Trigger Rule | SOP Applied | Remediation Workflow | Verification Predicate |
|---|---|---|---|---|---|---|
| **INC-001** | High CPU Utilization | `python -m scripts.simulate cpu` | `high_cpu` | `SOP-001` | Deprioritize with renice, terminate rogue worker | `cpu.percent < 70%` sustained |
| **INC-002** | High Memory Utilization | `python -m scripts.simulate memory` | `high_memory` | `SOP-002` | Audit top RSS consumers, terminate leaking process | `mem.percent` below threshold |
| **INC-003** | Disk Volume Exhaustion | `python -m scripts.simulate disk` | `disk_full_vol` | `SOP-003` | Locate largest files, purge rotated log files | `disk.vol.percent < 70%` |
| **INC-004** | Managed Service Outage | `python -m scripts.simulate service` | `service_down` | `SOP-004` | Inspect crash logs, restart service daemon | `/health` responds HTTP 200 |
| **INC-005** | DNS Resolution Failure | `python -m scripts.simulate dns` | `dns_failure` | `SOP-005` | Diagnose nameservers, switch to fallback resolver | `dns.up == 1` |
| **INC-006** | Network Dependency Down | `python -m scripts.simulate network` | `tcp_unreachable` | `SOP-006` | Probe transport port, restart upstream daemon | `conn.tcp_up == 1` on port 8082 |

---

## Repository Layout

```
infraops/
├── Makefile                       # Top-level operational targets (install, test, lint, demo)
├── pyproject.toml                 # Package dependencies and tool configuration
├── Dockerfile.server              # Container definition for central server
├── Dockerfile.agent               # Container definition for edge monitoring agent
├── docker-compose.yml             # Local multi-node test topology
├── config/
│   ├── alert_rules.yaml           # Production alert thresholds and sustain windows
│   ├── alert_rules.test.yaml      # Low-latency thresholds for fast deterministic testing
│   ├── agent.yaml                 # Agent collection frequencies and monitored services
│   └── server.yaml                # Server database, auth, and network settings
├── sops/                          # Declarative YAML runbooks (SOP-001 through SOP-006)
├── infra/
│   ├── terraform/                 # Reference AWS Infrastructure as Code specifications
│   │   ├── main.tf                # VPC, subnets, EC2, IAM, S3, CloudWatch definitions
│   │   ├── variables.tf           # Configurable infrastructure variables
│   │   ├── outputs.tf             # Resource IDs and endpoints
│   │   └── iam_policies/          # Least-privilege IAM policies
│   └── systemd/                   # Linux systemd service unit templates
├── infraops/
│   ├── common/                    # Shared configuration, schemas, logging, and sandbox guards
│   ├── agent/                     # Telemetry collectors, offline spooling shipper, and action API
│   ├── server/                    # Server core, database models, alerting, and SOP orchestrator
│   └── demo/                      # Managed HTTP service, TCP upstream, and supervisor
├── scripts/
│   ├── bash/                      # POSIX diagnostic shell utilities
│   ├── simulate/                  # Safe incident simulators with sandbox isolation
│   └── demo_run.py                # Autonomous end-to-end incident execution runner
├── docs/                          # Comprehensive technical documentation
│   ├── ARCHITECTURE.md            # System architecture and design principles
│   ├── RUNBOOK.md                 # Full manual CLI equivalents for each SOP
│   ├── SOP_AUTHORING.md           # SOP schema reference and creation guide
│   ├── INCIDENT_EXAMPLES.md       # Real post-mortem incident reports
│   ├── NETWORKING_NOTES.md        # TCP/IP, DNS, HTTP, and CIDR math notes
│   ├── COVERAGE.md                # Mapping of requirements to implementation files
│   ├── INTERVIEW_NOTES.md         # Interview questions, answers, and verbal scripts
│   └── DECISIONS.md               # Architectural decision records
└── tests/
    ├── unit/                      # Fast unit tests for collectors, rules, and sandbox
    ├── integration/               # Integration tests for server core and dashboard
    └── e2e/                       # End-to-end full incident verification suite
```

---

## Documentation Links

- [System Architecture & Components](docs/ARCHITECTURE.md)
- [Operational Runbook & Manual CLI Equivalents](docs/RUNBOOK.md)
- [SOP Authoring & Schema Reference](docs/SOP_AUTHORING.md)
- [Real Incident Post-Mortem Records](docs/INCIDENT_EXAMPLES.md)
- [Networking & Subnetting Engineering Notes](docs/NETWORKING_NOTES.md)
- [Checklist Requirement Coverage Map](docs/COVERAGE.md)
- [Interview Reference Notes & Scripts](docs/INTERVIEW_NOTES.md)
- [Architectural Decision Records](docs/DECISIONS.md)
