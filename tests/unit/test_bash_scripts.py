"""Unit tests for diagnostic bash scripts."""

import os
import shutil
import subprocess

import pytest

SCRIPTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "bash")
)

BASH_SCRIPTS = [
    "sys_snapshot.sh",
    "check_ports.sh",
    "check_dns.sh",
    "disk_report.sh",
    "log_scan.sh",
    "ssh_audit.sh",
    "perm_audit.sh",
    "bootstrap_agent.sh",
]


def get_bash_executable():
    """Find a functional bash executable on Windows (e.g. Git Bash) or Linux/macOS."""
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]
    sys_bash = shutil.which("bash")
    if sys_bash and "system32" not in sys_bash.lower():
        candidates.append(sys_bash)

    for b in candidates:
        if os.path.exists(b):
            try:
                res = subprocess.run([b, "-c", "exit 0"], capture_output=True, timeout=3)
                if res.returncode == 0:
                    return b
            except Exception:
                continue
    return None


BASH_PATH = get_bash_executable()


def test_scripts_exist_and_non_empty():
    """Verify all required bash scripts exist and have POSIX shebang."""
    for script_name in BASH_SCRIPTS:
        script_path = os.path.join(SCRIPTS_DIR, script_name)
        assert os.path.exists(script_path), f"Script {script_name} must exist"
        with open(script_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            assert first_line.startswith("#!/"), f"Script {script_name} must start with a shebang"


@pytest.mark.skipif(BASH_PATH is None, reason="Bash executable not available on this host")
@pytest.mark.parametrize("script_name", BASH_SCRIPTS)
def test_script_help_flag(script_name):
    """Verify every script responds to --help with return code 0."""
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    result = subprocess.run(
        [BASH_PATH, script_path, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"{script_name} --help failed: {result.stderr}"
    assert "Usage:" in result.stdout or "usage:" in result.stdout.lower()
