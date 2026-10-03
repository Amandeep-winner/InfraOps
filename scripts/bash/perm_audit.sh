#!/usr/bin/env bash
# perm_audit.sh - Audit critical file permissions and scan for world-writable paths
# Exit codes: 0 = audit complete, 1 = invalid arguments

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: perm_audit.sh [DIRECTORY...]

Audits permissions on critical Linux files (/etc/passwd, /etc/shadow, ~/.ssh)
and scans provided directories for world-writable files and directories.

Arguments:
  DIRECTORY...   Optional list of directories to scan for world-writable files

Options:
  --help, -h     Show this help message and exit
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi

echo "=== PERMISSIONS AND SECURITY AUDIT ==="
VIOLATIONS=0

check_file_perm() {
  local target="$1"
  local max_perm="$2"
  local expected_desc="$3"

  if [ -e "$target" ]; then
    local actual_perm
    actual_perm=$(stat -c "%a" "$target" 2>/dev/null || stat -f "%OLp" "$target" 2>/dev/null || echo "")
    local actual_owner
    actual_owner=$(stat -c "%U:%G" "$target" 2>/dev/null || echo "unknown")

    if [ -n "$actual_perm" ]; then
      if [ "$actual_perm" -le "$max_perm" ]; then
        echo "[PASS] $target: mode $actual_perm ($actual_owner) matches requirement <= $max_perm ($expected_desc)"
      else
        echo "[WARN] $target: mode $actual_perm ($actual_owner) exceeds max allowed $max_perm ($expected_desc)"
        VIOLATIONS=$((VIOLATIONS + 1))
      fi
    fi
  else
    echo "[SKIP] $target does not exist"
  fi
}

echo -e "\n--- CRITICAL SYSTEM FILES AUDIT ---"
check_file_perm "/etc/passwd" 644 "world-readable, root-writable only"
check_file_perm "/etc/shadow" 640 "restricted to root/shadow"
check_file_perm "/etc/gshadow" 640 "restricted to root/shadow"
check_file_perm "/etc/ssh/sshd_config" 644 "root-writable only"

SSH_DIR="${HOME:-/root}/.ssh"
if [ -d "$SSH_DIR" ]; then
  check_file_perm "$SSH_DIR" 700 "user directory only"
  if [ -f "$SSH_DIR/authorized_keys" ]; then
    check_file_perm "$SSH_DIR/authorized_keys" 600 "user-only rw"
  fi
fi

echo -e "\n--- WORLD-WRITABLE SCAN ---"
SCAN_DIRS=("$@")
if [ "${#SCAN_DIRS[@]}" -eq 0 ]; then
  SCAN_DIRS=("/tmp" "/var/tmp")
fi

for DIR in "${SCAN_DIRS[@]}"; do
  if [ -d "$DIR" ]; then
    echo "Scanning $DIR for world-writable items..."
    WW_COUNT=$(find "$DIR" -maxdepth 3 -perm -0002 \! -type l 2>/dev/null | grep -c -v '^$' || true)
    echo "Found $WW_COUNT world-writable path(s) in $DIR"
  fi
done

echo -e "\n=== AUDIT COMPLETE (Violations detected: $VIOLATIONS) ==="
exit 0
