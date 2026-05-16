#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <version> [--prerelease] [--draft] [--notes <text>]

Creates a Q-Box agent OTA release:
  1. packages agent into dist/qbox-agent-<version>.tar.gz
  2. generates manifest with SHA256
  3. creates/updates GitHub release
  4. uploads tar.gz and manifest assets

Configuration:
  export GITHUB_TOKEN=github_pat_xxx
  export GITHUB_REPO=Q-Home/Q-Central

Or create ~/.qcentral-release.env:
  GITHUB_TOKEN=github_pat_xxx
  GITHUB_REPO=Q-Home/Q-Central

Required GitHub permission:
  Contents: Read and write
USAGE
}

VERSION="${1:-}"
shift || true
PRERELEASE=false
DRAFT=false
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prerelease) PRERELEASE=true; shift ;;
    --draft) DRAFT=true; shift ;;
    --notes) NOTES="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  usage >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${QCENTRAL_RELEASE_ENV:-$HOME/.qcentral-release.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

: "${GITHUB_TOKEN:?GITHUB_TOKEN is required. Put it in ~/.qcentral-release.env or export it.}"
GITHUB_REPO="${GITHUB_REPO:-Q-Home/Q-Central}"
TAG="qbox-agent-${VERSION}"
RELEASE_NAME="Q-Box Agent ${VERSION}"
API="https://api.github.com/repos/${GITHUB_REPO}"
DIST_DIR="$ROOT_DIR/dist"
ARCHIVE="$DIST_DIR/qbox-agent-${VERSION}.tar.gz"
MANIFEST="$DIST_DIR/qbox-agent-${VERSION}.manifest.json"
TMP_DIR="$(mktemp -d /tmp/qcentral-release.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}
need_cmd curl
need_cmd python3
need_cmd sha256sum
need_cmd tar

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'
}

json_get() {
  local file="$1"
  local expr="$2"
  python3 - "$file" "$expr" <<'PY'
import json, sys
path, expr = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
value = data
for part in expr.split('.'):
    if not part:
        continue
    value = value[part]
print(value)
PY
}

json_find_asset_id() {
  local file="$1"
  local name="$2"
  python3 - "$file" "$name" <<'PY'
import json, sys
path, wanted = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    assets = json.load(f)
for asset in assets:
    if asset.get('name') == wanted:
        print(asset.get('id'))
        break
PY
}

api_call_file() {
  local method="$1"
  local url="$2"
  local output="$3"
  local data_file="${4:-}"
  local status_file="${output}.status"
  local http_code
  if [[ -n "$data_file" ]]; then
    http_code="$(curl -sS -X "$method" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -H "Content-Type: application/json" \
      --data-binary "@$data_file" \
      -o "$output" -w '%{http_code}' \
      "$url")"
  else
    http_code="$(curl -sS -X "$method" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -o "$output" -w '%{http_code}' \
      "$url")"
  fi
  printf '%s' "$http_code" > "$status_file"
  if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
    return 1
  fi
}

api_delete() {
  local url="$1"
  curl -fsSL -X DELETE \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$url" >/dev/null
}

upload_asset() {
  local release_id="$1"
  local file="$2"
  local name
  name="$(basename "$file")"
  local upload_url="https://uploads.github.com/repos/${GITHUB_REPO}/releases/${release_id}/assets?name=${name}"
  local assets_file="$TMP_DIR/assets.json"

  echo "[Q-Central] Removing existing asset if present: $name"
  api_call_file GET "${API}/releases/${release_id}/assets" "$assets_file"
  local existing_id
  existing_id="$(json_find_asset_id "$assets_file" "$name")"
  if [[ -n "$existing_id" ]]; then
    api_delete "${API}/releases/assets/${existing_id}"
  fi

  echo "[Q-Central] Uploading asset: $name"
  curl -fsSL -X POST \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@$file" \
    "$upload_url" >/dev/null
}

echo "[Q-Central] Packaging agent release $VERSION"
chmod +x "$ROOT_DIR/scripts/package-agent-release.sh"
"$ROOT_DIR/scripts/package-agent-release.sh" "$VERSION"

if [[ ! -f "$ARCHIVE" || ! -f "$MANIFEST" ]]; then
  echo "Package output missing: $ARCHIVE or $MANIFEST" >&2
  exit 1
fi

SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
if ! grep -q "$SHA256" "$MANIFEST"; then
  echo "Manifest does not contain expected SHA256" >&2
  exit 1
fi

if [[ -z "$NOTES" ]]; then
  NOTES="Q-Box agent OTA release ${VERSION}

Artifacts:
- qbox-agent-${VERSION}.tar.gz
- qbox-agent-${VERSION}.manifest.json

SHA256:
${SHA256}

This release is discoverable by Q-Central Software Repository."
fi

NOTES_JSON="$(printf '%s' "$NOTES" | json_escape)"
PAYLOAD_FILE="$TMP_DIR/release-payload.json"
cat > "$PAYLOAD_FILE" <<JSON
{
  "tag_name": "$TAG",
  "name": "$RELEASE_NAME",
  "body": $NOTES_JSON,
  "draft": $DRAFT,
  "prerelease": $PRERELEASE
}
JSON

RELEASE_ID=""
RELEASE_FILE="$TMP_DIR/release.json"
echo "[Q-Central] Checking GitHub release $TAG"
if api_call_file GET "${API}/releases/tags/${TAG}" "$RELEASE_FILE"; then
  RELEASE_ID="$(json_get "$RELEASE_FILE" id)"
  echo "[Q-Central] Updating existing release id $RELEASE_ID"
  api_call_file PATCH "${API}/releases/${RELEASE_ID}" "$RELEASE_FILE" "$PAYLOAD_FILE"
else
  echo "[Q-Central] Creating release $TAG"
  if ! api_call_file POST "${API}/releases" "$RELEASE_FILE" "$PAYLOAD_FILE"; then
    echo "GitHub release creation failed:" >&2
    cat "$RELEASE_FILE" >&2
    exit 1
  fi
  RELEASE_ID="$(json_get "$RELEASE_FILE" id)"
fi

upload_asset "$RELEASE_ID" "$ARCHIVE"
upload_asset "$RELEASE_ID" "$MANIFEST"

cat <<DONE

[Q-Central] Agent release published successfully
Repository: https://github.com/${GITHUB_REPO}
Release:    https://github.com/${GITHUB_REPO}/releases/tag/${TAG}
Version:    ${VERSION}
SHA256:     ${SHA256}

Open Q-Central > OTA Repository and click 'Releases ophalen'.
DONE
