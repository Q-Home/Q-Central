#!/usr/bin/env bash
set -euo pipefail
DEST="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"
if docker volume inspect deploy_qcentral-data >/dev/null 2>&1; then
  docker run --rm -v deploy_qcentral-data:/data:ro -v "$DEST":/backup alpine:3.20 sh -c "cd /data && tar czf /backup/qcentral-data-$STAMP.tar.gz ."
  echo "$DEST/qcentral-data-$STAMP.tar.gz"
else
  echo "Volume deploy_qcentral-data not found; skipping docker-volume backup" >&2
fi
