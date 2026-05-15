#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${Q_CENTRAL_APP_DIR:-/opt/Q-Central}"
COMPOSE_FILE="${Q_CENTRAL_COMPOSE_FILE:-docker-compose.production.yml}"
BRANCH="${Q_CENTRAL_BRANCH:-main}"
BACKUP_BEFORE_UPDATE="${Q_CENTRAL_BACKUP_BEFORE_UPDATE:-true}"
NO_CACHE="${Q_CENTRAL_BUILD_NO_CACHE:-false}"

log() {
  printf '\n[Q-Central] %s\n' "$*"
}

run() {
  printf '+ %s\n' "$*"
  "$@"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root or with sudo." >&2
  exit 1
fi

if [ ! -d "$APP_DIR/.git" ]; then
  echo "Repository not found at $APP_DIR" >&2
  exit 1
fi

if [ ! -f "$APP_DIR/deploy/.env" ]; then
  echo "Missing $APP_DIR/deploy/.env" >&2
  exit 1
fi

cd "$APP_DIR"

log "Current version"
git --no-pager log -1 --oneline || true

if [ "$BACKUP_BEFORE_UPDATE" = "true" ] && [ -x "$APP_DIR/scripts/backup-qcentral.sh" ]; then
  log "Running backup before update"
  "$APP_DIR/scripts/backup-qcentral.sh" || {
    echo "Backup failed. Aborting update." >&2
    exit 1
  }
else
  log "Backup skipped"
fi

log "Fetching latest code"
run git fetch origin "$BRANCH"

log "Resetting working tree to origin/$BRANCH"
run git reset --hard "origin/$BRANCH"

cd "$APP_DIR/deploy"

log "Validating compose config"
run docker compose -f "$COMPOSE_FILE" config >/tmp/qcentral-compose-config.yml

log "Pulling external images"
run docker compose -f "$COMPOSE_FILE" pull --ignore-buildable || true

log "Building local images"
if [ "$NO_CACHE" = "true" ]; then
  run docker compose -f "$COMPOSE_FILE" build --no-cache
else
  run docker compose -f "$COMPOSE_FILE" build
fi

log "Restarting stack"
run docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

log "Pruning unused Docker images"
run docker image prune -f || true

log "Waiting for API health"
for i in $(seq 1 30); do
  if docker compose -f "$COMPOSE_FILE" exec -T api python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()
PY
  then
    log "API is healthy"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "API healthcheck failed after update." >&2
    docker compose -f "$COMPOSE_FILE" logs --tail=120 api >&2 || true
    exit 1
  fi
  sleep 2
done

log "Running containers"
docker compose -f "$COMPOSE_FILE" ps

log "Update complete"
