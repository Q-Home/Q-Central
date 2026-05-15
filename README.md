# Q-Central

Production-ready selfhosted control plane for Q-Box devices over a ZeroTier overlay.

## Components

- **Central API**: provisioning, serial registry, auto authorization, customer mapping, OTA/job queue, app manager, inventory.
- **Frontend**: Q-Central dashboard.
- **Q-Box Agent**: lightweight Python agent installed on each Q-Box. It talks to Central over the ZeroTier overlay.
- **Deploy stack**: Docker Compose, Caddy reverse proxy, non-root containers, health checks, env validation and backup scripts.

## Production assumptions

- Central is reachable by agents on the ZeroTier overlay, e.g. `https://q-central.zt.q-home.local`.
- Public exposure is optional. Prefer access only through VPN/ZeroTier plus HTTPS.
- Device enrollment uses a serial + one-time claim token.
- After enrollment, each device receives its own agent token.
- Agent tokens are stored only on the Q-Box, never committed to Git.

## Quick production deploy

```bash
cd deploy
cp .env.production.example .env
nano .env
./start-production.sh
```

Then open:

```text
https://<Q_CENTRAL_HOSTNAME>
```

## First device provisioning

On Central, create a serial:

```bash
./scripts/create-serial.sh QBX-2026-0001 "Customer name" "Site name"
```

On the Q-Box:

```bash
curl -fsSL https://raw.githubusercontent.com/Q-Home/Q-Central/main/agent/install.sh | sudo bash -s -- \
  --central-url https://q-central.zt.q-home.local \
  --serial QBX-2026-0001 \
  --claim-token <claim-token>
```

## Repository layout

```text
backend/       FastAPI Central API
frontend/      React/Vite dashboard
agent/         Q-Box agent and install scripts
deploy/        Docker Compose production stack
scripts/       operational scripts
.github/       CI workflow
docs/          architecture and hardening notes
```

## Security baseline

- No default production secrets.
- Required env validation at startup.
- CORS allow-list.
- Rate limiting.
- Per-device tokens.
- One-time claim tokens.
- Audit log table.
- Non-root containers.
- Read-only frontend/reverse-proxy containers where possible.
- Health checks.
- Backups for the SQLite data volume.

See [`docs/HARDENING.md`](docs/HARDENING.md).


## Updates and redeploy

Agent and app updates are managed from Q-Central through OTA jobs over the ZeroTier overlay. Q-Central itself is updated separately at host level.

Queue an agent update:

```bash
curl -fsS -X POST "$QCENTRAL_URL/api/jobs/agent-update" \
  -H "X-Admin-Token: $QCENTRAL_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"serial":"QBX-2026-0001","url":"https://github.com/Q-Home/Q-Central/releases/download/agent-v1.0.1/qbox-agent-v1.0.1.tar.gz","sha256":"<sha256>","version":"1.0.1"}'
```

Update an app bundle on a Q-Box:

```bash
curl -fsS -X POST "$QCENTRAL_URL/api/jobs/app-update" \
  -H "X-Admin-Token: $QCENTRAL_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"serial":"QBX-2026-0001","path":"/storage/dockers/q-energy-ai","compose_file":"docker-compose.yml"}'
```

Update Q-Central itself on the Central host:

```bash
sudo ./scripts/update-central.sh --ref main --yes
```

See [`docs/UPDATES.md`](docs/UPDATES.md).

## Agent update from web UI

Open Q-Central, select one or more devices in **Device inventory**, fill in the agent release URL and SHA256, then click **Queue agent update**. This creates `agent_update` jobs that are pulled by agents through their normal heartbeat over the ZeroTier overlay.
