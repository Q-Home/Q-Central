#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version>" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
WORK_DIR="$(mktemp -d /tmp/qbox-agent-release.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

mkdir -p "$DIST_DIR"
mkdir -p "$WORK_DIR/agent"

cp -a "$ROOT_DIR/agent/qbox_agent" "$WORK_DIR/agent/"
cp "$ROOT_DIR/agent/requirements.txt" "$WORK_DIR/agent/"
cp "$ROOT_DIR/agent/update-agent.sh" "$WORK_DIR/agent/"
chmod +x "$WORK_DIR/agent/update-agent.sh"
printf '%s\n' "$VERSION" > "$WORK_DIR/agent/VERSION"

ARCHIVE="$DIST_DIR/qbox-agent-${VERSION}.tar.gz"
MANIFEST="$DIST_DIR/qbox-agent-${VERSION}.manifest.json"

tar -C "$WORK_DIR" -czf "$ARCHIVE" agent
SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
SIZE="$(stat -c '%s' "$ARCHIVE")"
CREATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$MANIFEST" <<JSON
{
  "name": "qbox-agent",
  "version": "$VERSION",
  "artifact": "qbox-agent-${VERSION}.tar.gz",
  "sha256": "$SHA256",
  "size_bytes": $SIZE,
  "created_at": "$CREATED_AT",
  "kind": "agent_update"
}
JSON

echo "Archive:  $ARCHIVE"
echo "Manifest: $MANIFEST"
echo "SHA256:   $SHA256"
