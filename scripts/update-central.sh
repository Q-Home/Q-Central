#!/usr/bin/env bash
set -euo pipefail

# Hardened Q-Central self-update/redeploy script.
# Intended to run on the Q-Central host, not inside the API container.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT_DIR/deploy"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.production.yml"
ENV_FILE="$DEPLOY_DIR/.env"
REF="${QCENTRAL_UPDATE_REF:-main}"
REMOTE="${QCENTRAL_UPDATE_REMOTE:-origin}"
HEALTH_URL="${QCENTRAL_HEALTH_URL:-http://127.0.0.1/healthz}"
BACKUP_DIR="${QCENTRAL_BACKUP_DIR:-$ROOT_DIR/backups}"
CONFIRM="${QCENTRAL_CONFIRM:-}"

usage() {
  cat <<USAGE
Usage: sudo ./scripts/update-central.sh [--ref main|tag|sha] [--yes]

Environment overrides:
  QCENTRAL_HEALTH_URL=http://127.0.0.1/healthz
  QCENTRAL_BACKUP_DIR=/var/backups/qcentral
  QCENTRAL_UPDATE_REMOTE=origin
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="${2:-}"; shift 2 ;;
    --yes) CONFIRM="yes"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -f "$COMPOSE_FILE" ]] || { echo "Missing compose file: $COMPOSE_FILE" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "Missing env file: $ENV_FILE" >&2; exit 1; }

if [[ "$CONFIRM" != "yes" ]]; then
  echo "This will update Q-Central to ref '$REF', rebuild/redeploy containers and run a health check."
  read -r -p "Continue? Type 'yes': " CONFIRM
  [[ "$CONFIRM" == "yes" ]] || exit 1
fi

mkdir -p "$BACKUP_DIR"
CURRENT_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "$CURRENT_SHA" > "$BACKUP_DIR/previous-sha.txt"

echo "[1/6] Backing up data volume"
"$ROOT_DIR/scripts/backup-central.sh" "$BACKUP_DIR"

echo "[2/6] Fetching source"
git -C "$ROOT_DIR" fetch --tags "$REMOTE"
git -C "$ROOT_DIR" checkout "$REF"

NEW_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)"
echo "[3/6] Running backend syntax check"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build api frontend

echo "[4/6] Deploying containers"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans

echo "[5/6] Health check: $HEALTH_URL"
for i in $(seq 1 30); do
  if curl -fsSL "$HEALTH_URL" >/dev/null; then
    echo "[6/6] Q-Central updated successfully: $CURRENT_SHA -> $NEW_SHA"
    exit 0
  fi
  sleep 2
done

echo "Health check failed. Rolling back to $CURRENT_SHA" >&2
git -C "$ROOT_DIR" checkout "$CURRENT_SHA"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build api frontend
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans
exit 1
