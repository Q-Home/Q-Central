#!/usr/bin/env bash
set -euo pipefail
SERIAL="${1:-}"
CENTRAL_URL="${2:-}"
CLAIM_TOKEN="${3:-dev-claim-token}"
if [ -z "$SERIAL" ] || [ -z "$CENTRAL_URL" ]; then
  echo "Usage: sudo ./install-agent.sh <serial> <central-url> [claim-token]"
  exit 1
fi
apt-get update
apt-get install -y python3 python3-venv python3-pip
mkdir -p /etc/qbox /opt/qbox-agent
printf '%s\n' "$SERIAL" > /etc/qbox/serial
printf '%s\n' "$CLAIM_TOKEN" > /etc/qbox/claim_token
cat > /etc/qbox/agent.env <<ENV
QBOX_SERIAL=$SERIAL
QBOX_CLAIM_TOKEN=$CLAIM_TOKEN
QBOX_CENTRAL_URL=$CENTRAL_URL
QBOX_HEARTBEAT_INTERVAL=30
ENV
cp -r qbox_agent requirements.txt /opt/qbox-agent/
python3 -m venv /opt/qbox-agent/.venv
/opt/qbox-agent/.venv/bin/pip install -r /opt/qbox-agent/requirements.txt
cp qbox-agent.service /etc/systemd/system/qbox-agent.service
systemctl daemon-reload
systemctl enable --now qbox-agent.service
systemctl status qbox-agent.service --no-pager
