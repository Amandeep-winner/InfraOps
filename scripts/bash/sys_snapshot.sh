#!/usr/bin/env bash
# sys_snapshot.sh - Capture comprehensive Linux system diagnostic snapshot
# Exit codes: 0 = success, 1 = error/invalid arguments

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: sys_snapshot.sh [OPTIONS]

Captures a diagnostic snapshot of the system including:
  - Hostname, uptime, and load averages
  - Memory and swap consumption (free -m)
  - Filesystem space and inode utilization (df -h, df -i)
  - Top 10 processes sorted by CPU and memory
  - Network socket stats and listening ports
  - Recent logins and failed systemd services

Options:
  --help, -h    Show this help message and exit
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

echo "=== SYSTEM SNAPSHOT ==="
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%SZ')"
echo "Hostname:  $(hostname 2>/dev/null || echo 'unknown')"

echo -e "\n--- UPTIME & LOAD ---"
uptime 2>/dev/null || cat /proc/loadavg 2>/dev/null || echo "Uptime unavailable"

echo -e "\n--- MEMORY USAGE (MB) ---"
if command -v free >/dev/null 2>&1; then
  free -m
else
  grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree' /proc/meminfo 2>/dev/null || echo "Memory stats unavailable"
fi

echo -e "\n--- DISK SPACE UTILIZATION ---"
df -h 2>/dev/null || echo "Disk usage unavailable"

echo -e "\n--- INODE UTILIZATION ---"
df -i 2>/dev/null || echo "Inode usage unavailable"

echo -e "\n--- TOP 10 CPU CONSUMERS ---"
if command -v ps >/dev/null 2>&1; then
  ps aux --sort=-%cpu 2>/dev/null | head -n 11 || ps -ef | head -n 11
else
  echo "ps command unavailable"
fi

echo -e "\n--- TOP 10 MEMORY CONSUMERS ---"
if command -v ps >/dev/null 2>&1; then
  ps aux --sort=-%mem 2>/dev/null | head -n 11 || ps -ef | head -n 11
else
  echo "ps command unavailable"
fi

echo -e "\n--- SOCKET STATISTICS ---"
if command -v ss >/dev/null 2>&1; then
  ss -s 2>/dev/null || true
  echo "Listening ports:"
  ss -tulpn 2>/dev/null || true
elif command -v netstat >/dev/null 2>&1; then
  netstat -tuln 2>/dev/null || true
else
  echo "Socket statistics unavailable"
fi

echo -e "\n--- RECENT LOGINS ---"
if command -v last >/dev/null 2>&1; then
  last -n 5 2>/dev/null || true
else
  echo "last command unavailable"
fi

echo -e "\n--- FAILED SERVICES ---"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --failed 2>/dev/null || true
else
  echo "systemd unavailable"
fi

echo "=== END OF SNAPSHOT ==="
exit 0
