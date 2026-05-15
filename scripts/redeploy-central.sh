#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT_DIR/deploy"
docker compose --env-file "$DEPLOY_DIR/.env" -f "$DEPLOY_DIR/docker-compose.production.yml" up -d --build --remove-orphans
curl -fsSL "${QCENTRAL_HEALTH_URL:-http://127.0.0.1/healthz}" >/dev/null
