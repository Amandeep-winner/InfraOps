#!/usr/bin/env bash
# check_ports.sh - Probe open TCP ports using nc or /dev/tcp
# Exit codes: 0 = all open, 1 = invalid arguments, 2 = one or more ports closed

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: check_ports.sh <host> <port...>

Checks whether one or more TCP ports are listening on the target host.

Arguments:
  host      Hostname or IP address to probe
  port...   One or more port numbers (1-65535)

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

HOST="$1"
shift
PORTS=("$@")
FAILED=0

for PORT in "${PORTS[@]}"; do
  if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "ERROR: Invalid port number: $PORT" >&2
    exit 1
  fi

  OPEN=0
  if command -v nc >/dev/null 2>&1; then
    if nc -z -w 2 "$HOST" "$PORT" >/dev/null 2>&1; then
      OPEN=1
    fi
  else
    # Fallback to bash built-in /dev/tcp
    if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$HOST/$PORT" >/dev/null 2>&1; then
      OPEN=1
    fi
  fi

  if [ "$OPEN" -eq 1 ]; then
    echo "PORT $PORT on $HOST: OPEN"
  else
    echo "PORT $PORT on $HOST: CLOSED or UNREACHABLE"
    FAILED=1
  fi
done

if [ "$FAILED" -ne 0 ]; then
  exit 2
fi

exit 0
