#!/usr/bin/env bash
set -euo pipefail

CENTRAL_URL=""
SERIAL=""
CLAIM_TOKEN=""
MODEL="Q-Box ARM64"
VERSION="dev"
RELEASE_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --central-url) CENTRAL_URL="${2:-}"; shift 2 ;;
    --serial) SERIAL="${2:-}"; shift 2 ;;
    --claim-token) CLAIM_TOKEN="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    --release-url) RELEASE_URL="${2:-}"; shift 2 ;;
    *) echo "Unknown arg $1" >&2; exit 1 ;;
  esac
done

[[ -n "$CENTRAL_URL" && -n "$SERIAL" && -n "$CLAIM_TOKEN" ]] || { echo "missing --central-url --serial --claim-token" >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }

apt-get update
apt-get install -y python3 python3-venv python3-pip curl rsync systemd tar
install -d -m 700 /etc/qbox-agent
install -d -m 755 /opt/qbox-agent
python3 -m venv /opt/qbox-agent/venv
/opt/qbox-agent/venv/bin/pip install --upgrade pip

WORKDIR="$(mktemp -d /tmp/qbox-agent-install.XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCRIPT_DIR/qbox_agent" ]]; then
  SRC="$SCRIPT_DIR"
elif [[ -n "$RELEASE_URL" ]]; then
  ARCHIVE="$WORKDIR/agent.tar.gz"
  curl -fsSL "$RELEASE_URL" -o "$ARCHIVE"
  tar -xzf "$ARCHIVE" -C "$WORKDIR"
  SRC="$(find "$WORKDIR" -maxdepth 3 -type d -name qbox_agent -print -quit | xargs -r dirname)"
else
  echo "Missing local qbox_agent package and no --release-url supplied" >&2
  exit 2
fi

[[ -n "${SRC:-}" && -d "$SRC/qbox_agent" ]] || { echo "Could not find qbox_agent package" >&2; exit 3; }

rsync -a --delete "$SRC/qbox_agent" /opt/qbox-agent/
cp "$SRC/requirements.txt" /opt/qbox-agent/requirements.txt
cp "$SRC/update-agent.sh" /opt/qbox-agent/update-agent.sh
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
  "interval": 60
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
