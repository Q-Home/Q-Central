from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import Session

from .config import get_settings
from .db import get_session
from .models import Device
from .schemas import RegisterSerialRequest, RegisterSerialResponse
from .security import hash_secret, new_token, require_admin
from .software import _agent_releases

router = APIRouter(prefix='/api/devices', tags=['Devices'])

ZEROTIER_NETWORK_ID = '9445e68adada0b99'


@router.post('/add', response_model=RegisterSerialResponse)
def add_device(body: RegisterSerialRequest, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    if session.get(Device, body.serial):
        raise HTTPException(status_code=409, detail='serial already exists')
    claim_token = new_token('claim')
    device = Device(serial=body.serial, claim_token_hash=hash_secret(claim_token), name=body.name, customer=body.customer, site=body.site, model=body.model)
    session.add(device)
    session.commit()
    return RegisterSerialResponse(serial=body.serial, claim_token=claim_token)


@router.post('/add-command')
def add_device_command(body: RegisterSerialRequest, session: Session = Depends(get_session), actor: str = Depends(require_admin)):
    result = add_device(body, session, actor)
    central = str(get_settings().external_url).rstrip('/')
    command = f"curl -fsSL {central}/api/devices/install.sh | sudo bash -s -- --central-url {central} --serial {result.serial} --claim-token {result.claim_token} --zerotier-network {ZEROTIER_NETWORK_ID}"
    return {'ok': True, 'serial': result.serial, 'claim_token': result.claim_token, 'install_command': command}


@router.get('/install.sh', response_class=PlainTextResponse)
def install_script():
    releases = _agent_releases()
    latest = releases.get('latest') or {}
    if not latest.get('ready'):
        raise HTTPException(status_code=502, detail='no ready qbox-agent release found')
    url = latest['url']
    sha256 = latest['sha256']
    version = latest.get('version') or 'unknown'
    script = f'''#!/usr/bin/env bash
set -euo pipefail
CENTRAL_URL=""
SERIAL=""
CLAIM_TOKEN=""
ZEROTIER_NETWORK="{ZEROTIER_NETWORK_ID}"
while [ $# -gt 0 ]; do
  case "$1" in
    --central-url) CENTRAL_URL="$2"; shift 2 ;;
    --serial) SERIAL="$2"; shift 2 ;;
    --claim-token) CLAIM_TOKEN="$2"; shift 2 ;;
    --zerotier-network) ZEROTIER_NETWORK="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" = "0" ] || {{ echo "Run as root" >&2; exit 1; }}
[ -n "$CENTRAL_URL" ] && [ -n "$SERIAL" ] && [ -n "$CLAIM_TOKEN" ] || {{ echo "Missing central url, serial or claim token" >&2; exit 2; }}
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl tar rsync ca-certificates
if ! command -v zerotier-cli >/dev/null 2>&1; then
  curl -fsSL https://install.zerotier.com | bash || true
fi
if command -v zerotier-cli >/dev/null 2>&1 && [ -n "$ZEROTIER_NETWORK" ]; then
  zerotier-cli join "$ZEROTIER_NETWORK" || true
fi
install -d -m 0755 /etc/qbox-agent /opt/qbox-agent
cat > /etc/qbox-agent/config.json <<JSON
{{"serial":"$SERIAL","claim_token":"$CLAIM_TOKEN","central_url":"${{CENTRAL_URL%/}}","firmware":"{version}"}}
JSON
chmod 0600 /etc/qbox-agent/config.json
workdir=$(mktemp -d /tmp/qbox-agent-install.XXXXXX)
trap 'rm -rf "$workdir"' EXIT
curl -fsSL {url!r} -o "$workdir/agent.tar.gz"
echo {sha256!r}'  '$workdir/agent.tar.gz | sha256sum -c -
tar -xzf "$workdir/agent.tar.gz" -C "$workdir"
if [ -d "$workdir/agent/qbox_agent" ]; then src="$workdir/agent"; else src=$(find "$workdir" -maxdepth 3 -type d -name qbox_agent -print -quit | xargs -r dirname); fi
[ -n "$src" ] && [ -d "$src/qbox_agent" ] || {{ echo "Agent package invalid" >&2; exit 3; }}
rsync -a --delete "$src/" /opt/qbox-agent/
python3 -m venv /opt/qbox-agent/venv
/opt/qbox-agent/venv/bin/pip install --upgrade pip
/opt/qbox-agent/venv/bin/pip install -r /opt/qbox-agent/requirements.txt
printf '%s\n' {version!r} > /etc/qbox-agent/version
cat > /etc/systemd/system/qbox-agent.service <<'UNIT'
[Unit]
Description=Q-Box Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/qbox-agent
ExecStart=/opt/qbox-agent/venv/bin/python -m qbox_agent
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
rm -f /etc/qbox-agent/agent-token
cd /opt/qbox-agent
/opt/qbox-agent/venv/bin/python -m qbox_agent --once --provision
systemctl enable --now qbox-agent.service
systemctl restart qbox-agent.service
sleep 2
systemctl --no-pager --full status qbox-agent.service | head -n 25 || true
echo "Q-Box agent installed and provisioned. Serial: $SERIAL"
'''
    return script
