# InfraOps - Infrastructure Monitoring & Incident Response Platform

InfraOps is a self-contained platform that monitors Linux and AWS-style infrastructure, detects problems, and executes runbook-driven L1 incident response.
It handles incidents across their complete lifecycle: detect -> investigate -> identify -> remediate -> verify -> close.
The platform provides an audit timeline, post-incident reports, and an interactive NOC dashboard.

## Core Capabilities

- System and network metric collectors with graceful degradation.
- Real-time alert engine with sustain windows, deduplication, and flapping guards.
- SOP runbook automation with safe sandboxed remediation and manual L1 approval gates.
- Simulated real-world incidents (CPU hog, memory hog, disk full, service crash, DNS failure, network partition).
- Mock AWS environment with EC2, VPC, IAM, S3, and CloudWatch integration.
- Responsive server-rendered NOC operations dashboard with offline canvas chart visualization.

## Quickstart

```bash
git clone https://github.com/Amandeep-winner/InfraOps.git
cd InfraOps
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m infraops.server.app
```
