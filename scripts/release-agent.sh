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

api_call() {
  local method="$1"
  local url="$2"
  local data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -fsSL -X "$method" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -H "Content-Type: application/json" \
      --data "$data" \
      "$url"
  else
    curl -fsSL -X "$method" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "$url"
  fi
}

upload_asset() {
  local release_id="$1"
  local file="$2"
  local name
  name="$(basename "$file")"
  local upload_url="https://uploads.github.com/repos/${GITHUB_REPO}/releases/${release_id}/assets?name=${name}"

  echo "[Q-Central] Removing existing asset if present: $name"
  local assets existing_id
  assets="$(api_call GET "${API}/releases/${release_id}/assets")"
  existing_id="$(python3 - <<PY
import json
assets=json.loads('''$assets''')
name='$name'
for a in assets:
    if a.get('name') == name:
        print(a.get('id'))
        break
PY
)"
  if [[ -n "$existing_id" ]]; then
    api_call DELETE "${API}/releases/assets/${existing_id}" >/dev/null
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
RELEASE_PAYLOAD="$(cat <<JSON
{
  "tag_name": "$TAG",
  "name": "$RELEASE_NAME",
  "body": $NOTES_JSON,
  "draft": $DRAFT,
  "prerelease": $PRERELEASE
}
JSON
)"

RELEASE_ID=""
echo "[Q-Central] Checking GitHub release $TAG"
if release_json="$(api_call GET "${API}/releases/tags/${TAG}" 2>/dev/null)"; then
  RELEASE_ID="$(python3 - <<PY
import json
print(json.loads('''$release_json''')['id'])
PY
)"
  echo "[Q-Central] Updating existing release id $RELEASE_ID"
  api_call PATCH "${API}/releases/${RELEASE_ID}" "$RELEASE_PAYLOAD" >/dev/null
else
  echo "[Q-Central] Creating release $TAG"
  release_json="$(api_call POST "${API}/releases" "$RELEASE_PAYLOAD")"
  RELEASE_ID="$(python3 - <<PY
import json
print(json.loads('''$release_json''')['id'])
PY
)"
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
