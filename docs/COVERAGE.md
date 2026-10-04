# Must-Demonstrate Checklist & Implementation Coverage

This document maps every requirement from Section 1.2 of `IMPLEMENTATION.md` to its concrete implementation files, automated test cases, and documentation in the repository.

---

## 1. Linux Systems Administration

| Requirement | Implementation Files | Verification Test Cases | Documentation Reference |
|---|---|---|---|
| **Processes** | `infraops/agent/collectors/processes.py`<br>`infraops/server/sop/actions.py` | `tests/unit/test_collectors.py`<br>`tests/unit/test_actions.py` | `docs/RUNBOOK.md#sop-001`<br>`docs/ARCHITECTURE.md` |
| **Services** | `infraops/agent/collectors/services.py`<br>`infraops/demo/supervisor.py` | `tests/unit/test_collectors.py`<br>`tests/unit/test_simulators.py` | `docs/RUNBOOK.md#sop-004`<br>`docs/RUNBOOK.md#sop-006` |
| **Filesystems** | `infraops/agent/collectors/disk.py`<br>`scripts/bash/disk_report.sh` | `tests/unit/test_collectors.py`<br>`tests/unit/test_bash_scripts.py` | `docs/RUNBOOK.md#sop-003` |
| **Permissions** | `infraops/agent/collectors/permissions.py`<br>`scripts/bash/perm_audit.sh` | `tests/unit/test_collectors.py`<br>`tests/unit/test_bash_scripts.py` | `docs/RUNBOOK.md#sop-003`<br>`docs/ARCHITECTURE.md` |
| **SSH Security** | `infraops/agent/collectors/ssh_security.py`<br>`scripts/bash/ssh_audit.sh` | `tests/unit/test_collectors.py`<br>`tests/unit/test_bash_scripts.py` | `docs/RUNBOOK.md`<br>`docs/NETWORKING_NOTES.md` |
| **Log Scanning** | `infraops/agent/collectors/logs.py`<br>`scripts/bash/log_scan.sh` | `tests/unit/test_collectors.py`<br>`tests/unit/test_bash_scripts.py` | `docs/RUNBOOK.md#sop-004` |

---

## 2. Networking Engineering

| Requirement | Implementation Files | Verification Test Cases | Documentation Reference |
|---|---|---|---|
| **TCP/IP & Sockets** | `infraops/agent/collectors/connectivity.py`<br>`infraops/demo/demo_upstream.py` | `tests/unit/test_collectors.py`<br>`tests/unit/test_simulators.py` | `docs/NETWORKING_NOTES.md#1-tcpip-protocol--socket-lifecycles` |
| **DNS Resolution** | `infraops/agent/collectors/dns.py`<br>`scripts/bash/check_dns.sh` | `tests/unit/test_collectors.py`<br>`tests/unit/test_bash_scripts.py` | `docs/NETWORKING_NOTES.md#2-domain-name-system-dns-architecture` |
| **HTTP / HTTPS** | `infraops/agent/collectors/http.py`<br>`infraops/demo/demo_service.py` | `tests/unit/test_collectors.py`<br>`tests/integration/test_server_core.py` | `docs/NETWORKING_NOTES.md#3-http--service-availability-checks` |
| **Port Probing** | `scripts/bash/check_ports.sh`<br>`infraops/server/api/tools.py` | `tests/unit/test_bash_scripts.py`<br>`tests/unit/test_aws.py` | `docs/NETWORKING_NOTES.md` |
| **CIDR & Subnetting** | `infraops/server/netutils/cidr.py`<br>`infraops/server/api/tools.py` | `tests/unit/test_cidr.py`<br>`tests/unit/test_aws.py` | `docs/NETWORKING_NOTES.md#4-cidr-subnetting--aws-5-reserved-ip-rules` |

---

## 3. Amazon Web Services (AWS) Architecture

| Requirement | Implementation Files | Verification Test Cases | Documentation Reference |
|---|---|---|---|
| **EC2 Workloads** | `infraops/server/aws/ec2.py`<br>`infraops/server/aws/client.py` | `tests/unit/test_aws.py`<br>`tests/integration/test_dashboard.py` | `docs/ARCHITECTURE.md`<br>`infra/terraform/main.tf` |
| **VPC & Subnets** | `infraops/server/aws/vpc.py`<br>`infraops/server/netutils/cidr.py` | `tests/unit/test_aws.py`<br>`tests/unit/test_cidr.py` | `docs/NETWORKING_NOTES.md`<br>`infra/terraform/main.tf` |
| **IAM Security** | `infraops/server/aws/iam.py`<br>`infra/terraform/iam_policies/` | `tests/unit/test_aws.py` | `infra/terraform/iam_policies/agent_policy.json` |
| **S3 Storage** | `infraops/server/aws/s3.py`<br>`infraops/server/incidents/reports.py` | `tests/unit/test_aws.py`<br>`tests/unit/test_incidents.py` | `docs/ARCHITECTURE.md`<br>`infra/terraform/main.tf` |
| **CloudWatch** | `infraops/server/aws/cloudwatch.py` | `tests/unit/test_aws.py` | `docs/ARCHITECTURE.md`<br>`infra/terraform/main.tf` |

---

## 4. Telemetry Monitoring & Time-Series Storage

| Requirement | Implementation Files | Verification Test Cases | Documentation Reference |
|---|---|---|---|
| **CPU Telemetry** | `infraops/agent/collectors/cpu.py` | `tests/unit/test_collectors.py` | `docs/RUNBOOK.md#sop-001` |
| **Memory Telemetry** | `infraops/agent/collectors/memory.py` | `tests/unit/test_collectors.py` | `docs/RUNBOOK.md#sop-002` |
| **Disk Volume Space** | `infraops/agent/collectors/disk.py` | `tests/unit/test_collectors.py` | `docs/RUNBOOK.md#sop-003` |
| **Network Traffic** | `infraops/agent/collectors/network.py` | `tests/unit/test_collectors.py` | `docs/NETWORKING_NOTES.md` |
| **Service Status** | `infraops/agent/collectors/services.py` | `tests/unit/test_collectors.py` | `docs/RUNBOOK.md#sop-004` |
| **Application Logs** | `infraops/agent/collectors/logs.py` | `tests/unit/test_collectors.py` | `docs/RUNBOOK.md#sop-004` |

---

## 5. Automation & Scripting

| Requirement | Implementation Files | Verification Test Cases | Documentation Reference |
|---|---|---|---|
| **Python Automation** | `infraops/agent/main.py`<br>`infraops/agent/shipper.py`<br>`infraops/server/sop/engine.py` | `tests/unit/test_sop_engine.py`<br>`tests/integration/test_server_core.py` | `docs/ARCHITECTURE.md`<br>`docs/SOP_AUTHORING.md` |
| **POSIX Bash Scripts** | `scripts/bash/sys_snapshot.sh`<br>`scripts/bash/check_ports.sh`<br>`scripts/bash/check_dns.sh`<br>`scripts/bash/disk_report.sh`<br>`scripts/bash/log_scan.sh`<br>`scripts/bash/ssh_audit.sh`<br>`scripts/bash/perm_audit.sh`<br>`scripts/bash/bootstrap_agent.sh` | `tests/unit/test_bash_scripts.py` | `docs/RUNBOOK.md`<br>`docs/ARCHITECTURE.md` |

---

## 6. L1 Incident Response Lifecycle

| Requirement | Implementation Files | Verification Test Cases | Documentation Reference |
|---|---|---|---|
| **6 Declarative SOPs** | `sops/SOP-001-high-cpu.yaml`<br>`sops/SOP-002-high-memory.yaml`<br>`sops/SOP-003-disk-full.yaml`<br>`sops/SOP-004-service-down.yaml`<br>`sops/SOP-005-dns-failure.yaml`<br>`sops/SOP-006-network-connectivity.yaml` | `tests/unit/test_sop_loader.py` | `docs/RUNBOOK.md`<br>`docs/SOP_AUTHORING.md` |
| **6 Fault Simulators** | `scripts/simulate/cpu_hog.py`<br>`scripts/simulate/mem_hog.py`<br>`scripts/simulate/disk_fill.py`<br>`scripts/simulate/service_down.py`<br>`scripts/simulate/dns_failure.py`<br>`scripts/simulate/net_connectivity.py` | `tests/unit/test_simulators.py` | `docs/INCIDENT_EXAMPLES.md` |
| **State Machine** | `infraops/server/incidents/service.py` | `tests/unit/test_incidents.py` | `docs/ARCHITECTURE.md` |
| **Audit Timeline** | `infraops/server/models.py`<br>`infraops/server/sop/engine.py` | `tests/unit/test_sop_engine.py`<br>`tests/integration/test_dashboard.py` | `docs/INCIDENT_EXAMPLES.md` |
| **Post-Mortem Reports**| `infraops/server/incidents/reports.py` | `tests/unit/test_incidents.py`<br>`tests/e2e/test_end_to_end.py` | `docs/INCIDENT_EXAMPLES.md` |
