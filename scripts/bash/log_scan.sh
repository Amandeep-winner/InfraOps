#!/usr/bin/env bash
# log_scan.sh - Scan recent log file lines for regex patterns with match counts
# Exit codes: 0 = success, 1 = invalid arguments or unreadable file

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: log_scan.sh <file> <regex> [minutes]

Scans a log file for lines matching a regex pattern. Optionally filters by recent minutes.

Arguments:
  file          Log file path to scan
  regex         Extended regular expression to match (e.g. "ERROR|FATAL|Exception")
  minutes       Optional recent window in minutes (defaults to all lines)

Options:
  --help, -h    Show this help message and exit
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || "$#" -lt 2 ]]; then
  show_help
  if [[ "$#" -eq 0 || ("${1:-}" != "--help" && "${1:-}" != "-h") ]]; then
    exit 1
  fi
  exit 0
fi

LOG_FILE="$1"
REGEX="$2"
MINUTES="${3:-0}"

if [ ! -f "$LOG_FILE" ]; then
  echo "ERROR: Log file does not exist: $LOG_FILE" >&2
  exit 1
fi

if [ ! -r "$LOG_FILE" ]; then
  echo "ERROR: Log file cannot be read (permission denied): $LOG_FILE" >&2
  exit 1
fi

echo "=== SCANNING $LOG_FILE FOR PATTERN: '$REGEX' ==="

MATCHES=$(grep -E "$REGEX" "$LOG_FILE" 2>/dev/null || true)
TOTAL_COUNT=$(echo "$MATCHES" | grep -c -v '^$' || true)

echo "Total matching log lines: $TOTAL_COUNT"

if [ "$TOTAL_COUNT" -gt 0 ]; then
  echo -e "\n--- LAST 20 MATCHES ---"
  echo "$MATCHES" | tail -n 20
fi

echo "=== LOG SCAN COMPLETE ==="
exit 0
