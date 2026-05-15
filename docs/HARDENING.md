# Production hardening checklist

## Network

- Keep Central reachable only through ZeroTier/VPN where possible.
- Use HTTPS even inside the overlay.
- Do not expose the ZeroTier controller API publicly.
- Restrict firewall to 80/443 and ZeroTier management ports as needed.

## Secrets

- Generate secrets with `openssl rand -hex 32`.
- Never commit `.env`.
- Rotate `Q_CENTRAL_ADMIN_TOKEN` after setup.
- Device claim tokens are one-time secrets.
- Device agent tokens are per-device secrets.

## Containers

- Non-root API and frontend containers.
- Dropped Linux capabilities.
- `no-new-privileges` enabled.
- Read-only filesystem where possible.
- Health checks enabled.

## Agent

- Agent config is stored under `/etc/qbox-agent` with mode `0600`.
- Shell jobs are disabled by default.
- Prefer typed jobs such as `compose_pull` over arbitrary shell.

## Backups

Run:

```bash
./scripts/backup.sh
```

Store backups outside the host.
