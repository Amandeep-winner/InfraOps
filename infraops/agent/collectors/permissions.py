"""Critical file permissions and security audit collector."""

import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class PermissionCollector(BaseCollector):
    """Audits critical system paths against expected Unix file permissions."""

    name = "permissions"

    # Default expected maximum permissions (octal)
    EXPECTED_PERMISSIONS = {
        "/etc/passwd": 0o644,
        "/etc/shadow": 0o640,
        "/etc/gshadow": 0o640,
        "/etc/ssh/sshd_config": 0o644,
    }

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        violations = 0
        findings: List[Dict[str, Any]] = []

        audit_paths = self.config.get(
            "audit_paths", ["/etc/passwd", "/etc/shadow", "/etc/ssh/sshd_config", "~/.ssh"]
        )

        for p_str in audit_paths:
            path = Path(p_str).expanduser()
            if not path.exists():
                findings.append({"path": str(path), "status": "missing"})
                continue

            try:
                st = path.stat()
                mode = stat.S_IMODE(st.st_mode)
                mode_octal_str = oct(mode)

                expected_max = self.EXPECTED_PERMISSIONS.get(str(path))
                if path.name == ".ssh":
                    expected_max = 0o700

                violation = False
                if expected_max is not None and mode > expected_max:
                    violation = True
                    violations += 1

                # Check world-writable
                if bool(st.st_mode & stat.S_IWOTH):
                    violation = True
                    violations += 1

                findings.append(
                    {
                        "path": str(path),
                        "status": "violation" if violation else "ok",
                        "actual_mode": mode_octal_str,
                        "expected_max": oct(expected_max) if expected_max else "none",
                        "is_world_writable": bool(st.st_mode & stat.S_IWOTH),
                    }
                )
            except Exception as e:
                findings.append({"path": str(path), "status": f"error: {e}"})

        metrics = [MetricPoint(name="perm.violations", value=float(violations), ts=now)]
        snapshot = SnapshotPayload(
            kind="permissions", payload={"findings": findings, "violations": violations}, ts=now
        )
        return metrics, snapshot, []
