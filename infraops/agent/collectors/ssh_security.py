"""SSH configuration audit and authentication log inspector."""

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import paramiko

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


def remote_probe(
    host: str,
    username: str = "root",
    key_filename: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """Run sys_snapshot.sh on a remote server over SSH via Paramiko."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            username=username,
            key_filename=key_filename,
            password=password,
            timeout=5,
        )
        _, stdout, stderr = client.exec_command("bash -s", timeout=10)
        # Pass snapshot script over stdin
        script_path = Path(__file__).resolve().parents[3] / "scripts" / "bash" / "sys_snapshot.sh"
        if script_path.exists():
            with script_path.open("r", encoding="utf-8") as f:
                stdin_stream = client.exec_command(f.read())[0]
                stdin_stream.close()
        return stdout.read().decode("utf-8")
    finally:
        client.close()


class SshSecurityCollector(BaseCollector):
    """Audits local sshd_config parameters and inspects auth logs for login failures."""

    name = "ssh_security"

    def _parse_sshd_config(self, path: Path) -> Dict[str, Any]:
        findings = {
            "root_login_allowed": False,
            "password_auth_allowed": True,
            "port": 22,
            "status": "ok",
        }
        if not path.is_file():
            findings["status"] = "unavailable"
            return findings

        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        key, val = parts[0].lower(), parts[1].strip()
                        if key == "permitrootlogin":
                            findings["root_login_allowed"] = val.lower() not in [
                                "no",
                                "prohibit-password",
                                "without-password",
                            ]
                        elif key == "passwordauthentication":
                            findings["password_auth_allowed"] = val.lower() != "no"
                        elif key == "port":
                            try:
                                findings["port"] = int(val)
                            except ValueError:
                                pass
        except Exception as e:
            findings["status"] = f"error: {e}"

        return findings

    def _count_recent_failures(self, path: Path) -> int:
        if not path.is_file():
            return 0
        count = 0
        failure_pattern = re.compile(r"Failed password|Invalid user", re.IGNORECASE)
        try:
            # Read last 1000 lines
            with path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-1000:]
                for line in lines:
                    if failure_pattern.search(line):
                        count += 1
        except Exception:
            return 0
        return count

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []

        cfg_path = Path(self.config.get("sshd_config", "/etc/ssh/sshd_config"))
        auth_log_path = Path(self.config.get("auth_log", "/var/log/auth.log"))

        ssh_findings = self._parse_sshd_config(cfg_path)
        failed_count = self._count_recent_failures(auth_log_path)

        metrics.append(MetricPoint(name="ssh.failed_logins_5m", value=float(failed_count), ts=now))
        metrics.append(
            MetricPoint(
                name="ssh.root_login_enabled",
                value=1.0 if ssh_findings.get("root_login_allowed") else 0.0,
                ts=now,
            )
        )
        metrics.append(
            MetricPoint(
                name="ssh.password_auth_enabled",
                value=1.0 if ssh_findings.get("password_auth_allowed") else 0.0,
                ts=now,
            )
        )

        snapshot = SnapshotPayload(
            kind="ssh_security",
            payload={
                "sshd_config": ssh_findings,
                "failed_logins_recent": failed_count,
            },
            ts=now,
        )

        return metrics, snapshot, []
