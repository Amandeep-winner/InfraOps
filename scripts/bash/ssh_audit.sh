#!/usr/bin/env bash
# ssh_audit.sh - Audit SSH server configuration and failed login attempts
# Exit codes: 0 = success, 1 = error/invalid arguments

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: ssh_audit.sh [OPTIONS]

Audits SSH daemon configuration for security best practices and inspects
auth logs for brute force or failed authentication attempts.

Options:
  --config <path>   Path to sshd_config (default: /etc/ssh/sshd_config)
  --auth-log <path> Path to auth log (default: /var/log/auth.log or /var/log/secure)
  --help, -h        Show this help message and exit
EOF
}

SSHD_CONFIG="/etc/ssh/sshd_config"
AUTH_LOG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      SSHD_CONFIG="$2"
      shift 2
      ;;
    --auth-log)
      AUTH_LOG="$2"
      shift 2
      ;;
    --help|-h)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help
      exit 1
      ;;
  esac
done

echo "=== SSH SECURITY AUDIT ==="

echo -e "\n--- SSH DAEMON CONFIGURATION AUDIT ---"
if [ -f "$SSHD_CONFIG" ] && [ -r "$SSHD_CONFIG" ]; then
  echo "Auditing config file: $SSHD_CONFIG"
  
  # Check PermitRootLogin
  ROOT_LOGIN=$(grep -E '^\s*PermitRootLogin' "$SSHD_CONFIG" | tail -n 1 | awk '{print $2}' || true)
  if [[ "$ROOT_LOGIN" =~ ^(no|prohibit-password|without-password)$ ]]; then
    echo "[PASS] PermitRootLogin: $ROOT_LOGIN"
  elif [ -n "$ROOT_LOGIN" ]; then
    echo "[WARN] PermitRootLogin is enabled: $ROOT_LOGIN"
  else
    echo "[INFO] PermitRootLogin not explicitly set in config (check default)"
  fi

  # Check PasswordAuthentication
  PASS_AUTH=$(grep -E '^\s*PasswordAuthentication' "$SSHD_CONFIG" | tail -n 1 | awk '{print $2}' || true)
  if [[ "$PASS_AUTH" =~ ^no$ ]]; then
    echo "[PASS] PasswordAuthentication: no (Key-based only)"
  elif [ -n "$PASS_AUTH" ]; then
    echo "[WARN] PasswordAuthentication is enabled: $PASS_AUTH"
  else
    echo "[INFO] PasswordAuthentication not explicitly set"
  fi

  # Check Port
  PORT=$(grep -E '^\s*Port' "$SSHD_CONFIG" | tail -n 1 | awk '{print $2}' || true)
  echo "[INFO] Configured SSH Port: ${PORT:-22 (default)}"
else
  echo "[SKIP] sshd_config not found or not readable: $SSHD_CONFIG"
fi

echo -e "\n--- AUTHENTICATION LOG AUDIT ---"
# Detect auth log if not provided
if [ -z "$AUTH_LOG" ]; then
  if [ -f "/var/log/auth.log" ]; then
    AUTH_LOG="/var/log/auth.log"
  elif [ -f "/var/log/secure" ]; then
    AUTH_LOG="/var/log/secure"
  fi
fi

if [ -n "$AUTH_LOG" ] && [ -f "$AUTH_LOG" ] && [ -r "$AUTH_LOG" ]; then
  echo "Inspecting auth log: $AUTH_LOG"
  FAILED_COUNT=$(grep -E -c 'Failed password|Invalid user' "$AUTH_LOG" 2>/dev/null || true)
  echo "Total failed login events found: $FAILED_COUNT"
  if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "Recent failed logins:"
    grep -E 'Failed password|Invalid user' "$AUTH_LOG" | tail -n 10 || true
  fi
else
  echo "[SKIP] Auth log not found or unreadable: ${AUTH_LOG:-none detected}"
fi

echo -e "\n=== SSH AUDIT COMPLETE ==="
exit 0
