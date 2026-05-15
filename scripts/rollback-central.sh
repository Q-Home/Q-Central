#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${QCENTRAL_BACKUP_DIR:-$ROOT_DIR/backups}"
PREV="$(cat "$BACKUP_DIR/previous-sha.txt")"
[[ -n "$PREV" ]] || { echo "No previous SHA found" >&2; exit 1; }
git -C "$ROOT_DIR" checkout "$PREV"
"$ROOT_DIR/scripts/redeploy-central.sh"
