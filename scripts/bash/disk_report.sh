#!/usr/bin/env bash
# disk_report.sh - Generate disk usage, top directories, and largest files report
# Exit codes: 0 = success, 1 = invalid arguments or directory error

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: disk_report.sh <path>

Inspects disk utilization, identifies top directory space consumers, and finds largest files.

Arguments:
  path          Target directory path to inspect

Options:
  --help, -h    Show this help message and exit
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "$#" -lt 1 ]]; then
  show_help
  if [[ "$#" -eq 0 || ("${1:-}" != "--help" && "${1:-}" != "-h") ]]; then
    exit 1
  fi
  exit 0
fi

TARGET_PATH="$1"

if [ ! -d "$TARGET_PATH" ]; then
  echo "ERROR: Target directory does not exist: $TARGET_PATH" >&2
  exit 1
fi

echo "=== DISK UTILIZATION REPORT FOR: $TARGET_PATH ==="

echo -e "\n--- FILESYSTEM CAPACITY ---"
df -h "$TARGET_PATH" 2>/dev/null || echo "Filesystem info unavailable"

echo -e "\n--- TOTAL DIRECTORY CONSUMPTION ---"
du -sh "$TARGET_PATH" 2>/dev/null || echo "Directory size unavailable"

echo -e "\n--- TOP DIRECTORIES BY SIZE (DEPTH 1) ---"
if command -v du >/dev/null 2>&1; then
  du -h -d 1 "$TARGET_PATH" 2>/dev/null | sort -hr | head -n 10 || true
fi

echo -e "\n--- TOP 10 LARGEST FILES ---"
if command -v find >/dev/null 2>&1; then
  find "$TARGET_PATH" -type f -exec ls -lh {} + 2>/dev/null | awk '{print $5, $9}' | sort -hr | head -n 10 || true
fi

echo "=== END OF DISK REPORT ==="
exit 0
