# Q-Box Central

Selfhosted beheerplatform voor Q-Box devices via een ZeroTier overlay.

## Componenten

- `central-api`: FastAPI backend met provisioning API, serial registry, auto authorization, customer mapping, OTA queue, app manager en device inventory.
- `central-web`: React dashboard voor test/development.
- `agent`: Python agent voor de Q-Box. De agent praat via de ZeroTier overlay met Q-Box Central.
- `scripts`: helper scripts voor provisioning en testdata.
- `deploy`: Docker Compose voorbeeld voor testdeploy.

## Snelle testdeploy

```bash
cd deploy
cp .env.example .env
./start.sh
```

Dashboard:

- API: `http://localhost:8080`
- API docs: `http://localhost:8080/docs`
- Web UI: `http://localhost:5173`

## Test device registreren

```bash
./scripts/register-serial.sh QBX-2026-0001 "Q-Box Demo" "Q-Home" "Lab"
```

## Agent lokaal testen

```bash
cd agent
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
QBOX_SERIAL=QBX-2026-0001 \
QBOX_CENTRAL_URL=http://127.0.0.1:8080 \
QBOX_CLAIM_TOKEN=dev-claim-token \
python -m qbox_agent
```

## Productie-notities

Voor productie zet je Central best achter Caddy of Traefik met HTTPS. Binnen de ZeroTier overlay kan de agent de Central API bereiken via het private overlay-IP of een interne DNS-naam zoals `https://central.qbox.zt`.

Gebruik per device een uniek claim token. De meegeleverde `dev-claim-token` is alleen voor testdeploy.
