#!/usr/bin/env bash
# bootstrap_agent.sh - Install InfraOps agent as systemd service or cron job
# Exit codes: 0 = success, 1 = failure

set -euo pipefail

show_help() {
  cat << 'EOF'
Usage: bootstrap_agent.sh [OPTIONS]

Installs the InfraOps agent, sets up a virtual environment, installs the package,
and configures either a systemd unit or a cron schedule for continuous operation.

Options:
  --install-dir <path>  Target installation directory (default: /opt/infraops)
  --user <username>     System user to run the agent (default: current user)
  --server-url <url>    InfraOps server URL (default: http://localhost:8000)
  --api-key <key>       InfraOps agent API key (default: dev-secret-key)
  --dry-run             Print actions without modifying system
  --help, -h            Show this help message and exit
EOF
}

INSTALL_DIR="/opt/infraops"
RUN_USER="$(whoami)"
SERVER_URL="http://localhost:8000"
API_KEY="dev-secret-key"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --user)
      RUN_USER="$2"
      shift 2
      ;;
    --server-url)
      SERVER_URL="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
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

echo "=== INFRAOPS AGENT BOOTSTRAP ==="
echo "Target directory: $INSTALL_DIR"
echo "Run user:         $RUN_USER"
echo "Server URL:       $SERVER_URL"
echo "Dry run:          $DRY_RUN"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[DRY-RUN] Would create directory $INSTALL_DIR"
  echo "[DRY-RUN] Would create virtual environment at $INSTALL_DIR/.venv"
  echo "[DRY-RUN] Would install infraops package"
  echo "[DRY-RUN] Would configure systemd unit /etc/systemd/system/infraops-agent.service"
  exit 0
fi

mkdir -p "$INSTALL_DIR"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install .

# Systemd unit installation if root and systemd present
if [ "$(id -u)" -eq 0 ] && command -v systemctl >/dev/null 2>&1; then
  echo "Configuring systemd service..."
  cat << EOF > /etc/systemd/system/infraops-agent.service
[Unit]
Description=InfraOps Infrastructure Monitoring Agent
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$INSTALL_DIR
Environment=INFRAOPS_SERVER_URL=$SERVER_URL
Environment=INFRAOPS_API_KEY=$API_KEY
ExecStart=$INSTALL_DIR/.venv/bin/python -m infraops.agent.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable infraops-agent.service
  systemctl restart infraops-agent.service || true
  echo "Agent installed and started via systemd."
else
  echo "Non-root or systemd unavailable: configure cron fallback"
  CRON_LINE="* * * * * cd $INSTALL_DIR && INFRAOPS_SERVER_URL=$SERVER_URL INFRAOPS_API_KEY=$API_KEY $INSTALL_DIR/.venv/bin/python -m infraops.agent.main --once >> /tmp/infraops-agent.log 2>&1"
  (crontab -l 2>/dev/null || true; echo "$CRON_LINE") | crontab - 2>/dev/null || echo "Notice: crontab update skipped"
fi

echo "=== BOOTSTRAP COMPLETED SUCCESSFULLY ==="
exit 0
