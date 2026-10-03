# Architecture and Implementation Decisions

This log tracks architectural and technical decisions made during the autonomous build of InfraOps.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-04 | Use SQLite with WAL mode for embedded storage | Simplifies zero-dependency setup while providing reliable concurrent read performance for ingest and dashboard. |
| 2026-10-04 | Vendor minimal standalone Chart.js canvas fallback in plain JavaScript | Eliminates external CDN dependencies so the dashboard operates fully offline and in air-gapped environments. |
| 2026-10-04 | Provide Windows and cross-platform fallbacks for Linux-specific system metrics and signals | Allows agents and simulation tests to run cleanly on Windows workstations as well as Linux hosts and containers. |
| 2026-10-04 | Isolate all remediation and simulation writes to ./sandbox directory | Strictly enforces safety guardrails to prevent accidental mutation of system files or host processes. |
