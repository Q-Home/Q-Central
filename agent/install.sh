#!/usr/bin/env bash
set -euo pipefail

CENTRAL_URL=""
SERIAL=""
CLAIM_TOKEN=""
MODEL="Q-Box ARM64"
VERSION="dev"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --central-url) CENTRAL_URL="${2:-}"; shift 2 ;;
    --serial) SERIAL="${2:-}"; shift 2 ;;
    --claim-token) CLAIM_TOKEN="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    *) echo "Unknown arg $1" >&2; exit 1 ;;
  esac
done

[[ -n "$CENTRAL_URL" && -n "$SERIAL" && -n "$CLAIM_TOKEN" ]] || { echo "missing --central-url --serial --claim-token" >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }

apt-get update
apt-get install -y python3 python3-venv python3-pip curl rsync systemd
install -d -m 700 /etc/qbox-agent
install -d -m 755 /opt/qbox-agent
python3 -m venv /opt/qbox-agent/venv
/opt/qbox-agent/venv/bin/pip install --upgrade pip

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/qbox_agent" ]]; then
  rsync -a --delete "$SCRIPT_DIR/qbox_agent" /opt/qbox-agent/
  cp "$SCRIPT_DIR/requirements.txt" /opt/qbox-agent/requirements.txt
  cp "$SCRIPT_DIR/update-agent.sh" /opt/qbox-agent/update-agent.sh
else
  echo "Local qbox_agent package not found next to install.sh. Install from release archive instead." >&2
  exit 2
fi
chmod +x /opt/qbox-agent/update-agent.sh
/opt/qbox-agent/venv/bin/pip install -r /opt/qbox-agent/requirements.txt

echo "$VERSION" > /etc/qbox-agent/version
cat >/etc/qbox-agent/config.json <<JSON
{
  "central_url": "$CENTRAL_URL",
  "serial": "$SERIAL",
  "claim_token": "$CLAIM_TOKEN",
  "model": "$MODEL",
  "firmware": "$VERSION",
  "interval": 60,
  "allow_shell_jobs": false
}
JSON
chmod 600 /etc/qbox-agent/config.json

cat >/etc/systemd/system/qbox-agent.service <<'UNIT'
[Unit]
Description=Q-Box Central Agent
After=network-online.target zerotier-one.service docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/qbox-agent/venv/bin/python -m qbox_agent
Restart=always
RestartSec=10
User=root
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/etc/qbox-agent /storage/dockers /opt/qbox-agent /run

[Install]
WantedBy=multi-user.target
UNIT

PYTHONPATH=/opt/qbox-agent /opt/qbox-agent/venv/bin/python -m qbox_agent --provision --once
systemctl daemon-reload
systemctl enable --now qbox-agent
