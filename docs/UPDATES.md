# Q-Central update and redeploy design

This repository contains two separate update flows. They are intentionally not mixed.

## 1. Updating Q-Box agents from Q-Central

Q-Central queues a device job. The Q-Box agent receives the job during its heartbeat over the ZeroTier overlay.

Flow:

```text
Q-Central API -> Job queue -> Q-Box agent heartbeat -> systemd-run self update -> restart qbox-agent
```

Supported job types:

| Job kind | Purpose |
|---|---|
| `agent_update` | Update the Q-Box agent itself from a signed/checksummed tarball. |
| `app_update` | Pull and redeploy a Docker Compose app bundle on the Q-Box. |
| `app_restart` | Restart one app service. |
| `compose_pull` | Pull and redeploy a compose project. |
| `shell` | Disabled by default. Only enable for break-glass maintenance. |

### Queue an agent update

```bash
curl -fsS -X POST "$QCENTRAL_URL/api/jobs/agent-update" \
  -H "X-Admin-Token: $QCENTRAL_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "serial":"QBX-2026-0001",
    "url":"https://github.com/Q-Home/Q-Central/releases/download/agent-v1.0.1/qbox-agent-v1.0.1.tar.gz",
    "sha256":"<sha256>",
    "version":"1.0.1"
  }'
```

The agent calls `/opt/qbox-agent/update-agent.sh` through `systemd-run`. This prevents the running agent process from killing itself halfway through the update.

## 2. Updating apps on a Q-Box from Q-Central

```bash
curl -fsS -X POST "$QCENTRAL_URL/api/jobs/app-update" \
  -H "X-Admin-Token: $QCENTRAL_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "serial":"QBX-2026-0001",
    "path":"/storage/dockers/q-energy-ai",
    "compose_file":"docker-compose.yml"
  }'
```

The agent only accepts compose paths under:

```text
/storage/dockers
/opt/qbox-apps
```

This blocks accidental or malicious redeploys outside the Q-Box app area.

## 3. Updating Q-Central itself

Q-Central self-update is a host-level operation, not a normal device OTA job.

Use:

```bash
sudo ./scripts/update-central.sh --ref main --yes
```

The script does:

1. backup data volume;
2. remember previous Git SHA;
3. fetch source;
4. checkout requested ref/tag/SHA;
5. rebuild API and frontend containers;
6. redeploy with Docker Compose;
7. health check;
8. rollback to the previous SHA if health check fails.

Manual redeploy without Git update:

```bash
sudo ./scripts/redeploy-central.sh
```

Rollback to previous SHA:

```bash
sudo ./scripts/rollback-central.sh
```

## Production recommendation

Use GitHub releases/tags instead of deploying directly from `main`:

```text
q-central-v1.0.3
qbox-agent-v1.0.3
q-energy-ai-v1.8.2
```

For production, release artifacts should be checksummed and preferably signed.

## Agent updates via web UI

The Q-Central dashboard contains an **Agent update vanuit Q-Central** panel.

Flow:

1. Admin logs in with `X-Admin-Token` through the web UI.
2. Admin selects one or more devices in the inventory table.
3. Admin enters:
   - target version,
   - release artifact URL,
   - SHA256 checksum.
4. The UI creates one `agent_update` job per selected serial using `/api/jobs/agent-update`.
5. Each Q-Box agent receives the job during its next heartbeat over the ZeroTier overlay.
6. The agent downloads the artifact, verifies SHA256 when supplied, runs `update-agent.sh` through `systemd-run`, and reports the result back to Q-Central.

For production releases, publish agent artifacts under GitHub Releases and always include a SHA256 checksum.
