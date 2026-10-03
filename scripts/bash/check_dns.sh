#!/usr/bin/env bash
# check_dns.sh - Test DNS name resolution using dig, nslookup, or getent
# Exit codes: 0 = success, 1 = invalid arguments, 2 = resolution failed

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: check_dns.sh <name> [resolver]

Resolves a DNS domain name against an optional custom DNS resolver server.

Arguments:
  name       Domain name or hostname to query
  resolver   Optional DNS server IP address (e.g. 8.8.8.8)

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

NAME="$1"
RESOLVER="${2:-}"
RESOLVED=0

echo "Checking DNS resolution for: $NAME (Resolver: ${RESOLVER:-system default})"

if command -v dig >/dev/null 2>&1; then
  CMD=("dig" "+short" "+time=2" "+tries=1" "$NAME")
  if [ -n "$RESOLVER" ]; then
    CMD+=("@$RESOLVER")
  fi
  RESULT=$("${CMD[@]}" 2>/dev/null || true)
  if [ -n "$RESULT" ]; then
    echo "RESOLVED (dig):"
    echo "$RESULT"
    RESOLVED=1
  fi
elif command -v nslookup >/dev/null 2>&1; then
  CMD=("nslookup" "$NAME")
  if [ -n "$RESOLVER" ]; then
    CMD+=("$RESOLVER")
  fi
  RESULT=$("${CMD[@]}" 2>/dev/null || true)
  if echo "$RESULT" | grep -E -q '(Address|Name):'; then
    echo "RESOLVED (nslookup):"
    echo "$RESULT"
    RESOLVED=1
  fi
elif command -v getent >/dev/null 2>&1; then
  RESULT=$(getent hosts "$NAME" 2>/dev/null || true)
  if [ -n "$RESULT" ]; then
    echo "RESOLVED (getent):"
    echo "$RESULT"
    RESOLVED=1
  fi
fi

if [ "$RESOLVED" -eq 1 ]; then
  exit 0
else
  echo "DNS RESOLUTION FAILED for $NAME" >&2
  exit 2
fi
