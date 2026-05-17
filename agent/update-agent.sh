#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: sudo update-agent.sh --url <tar.gz-url> [--sha256 <hex>] [--version <version>] [--central-url <url>] [--job-id <id>] [--agent-token-file <path>]

The archive must contain an agent/ directory or qbox_agent/ package.
This script is designed to be called by qbox-agent itself through a systemd-run wrapper.
If central/job/token are provided, the script reports final OTA status back to Q-Central.
USAGE
}

URL=""
SHA256=""
VERSION=""
CENTRAL_URL=""
JOB_ID=""
AGENT_TOKEN_FILE="/etc/qbox-agent/agent-token"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="${2:-}"; shift 2 ;;
    --sha256) SHA256="${2:-}"; shift 2 ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    --central-url) CENTRAL_URL="${2:-}"; shift 2 ;;
    --job-id) JOB_ID="${2:-}"; shift 2 ;;
    --agent-token-file) AGENT_TOKEN_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
[[ -n "$URL" ]] || { echo "--url is required" >&2; exit 2; }

report_status() {
  local status="$1"
  local stage="$2"
  local progress="$3"
  local output="$4"
  if [[ -z "$CENTRAL_URL" || -z "$JOB_ID" || ! -f "$AGENT_TOKEN_FILE" ]]; then
    return 0
  fi
  local token
  token="$(cat "$AGENT_TOKEN_FILE")"
  python3 - <<PY || true
import json, urllib.request
url = "${CENTRAL_URL%/}/api/jobs/${JOB_ID}/result"
payload = {
  "status": "$status",
  "stage": "$stage",
  "progress": int($progress),
  "output": "$output"[-6000:],
}
req = urllib.request.Request(
  url,
  data=json.dumps(payload).encode("utf-8"),
  headers={"Content-Type": "application/json", "X-Agent-Token": "$token"},
  method="POST",
)
urllib.request.urlopen(req, timeout=20).read()
PY
}

WORKDIR="$(mktemp -d /tmp/qbox-agent-update.XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT
ARCHIVE="$WORKDIR/agent.tar.gz"

on_error() {
  local rc=$?
  report_status "failed" "failed" 100 "qbox-agent self-update failed with exit code ${rc}"
  exit "$rc"
}
trap on_error ERR

report_status "downloading" "downloading" 20 "Downloading agent artifact"
curl -fsSL "$URL" -o "$ARCHIVE"

if [[ -n "$SHA256" ]]; then
  report_status "downloading" "verifying" 40 "Verifying SHA256"
  echo "$SHA256  $ARCHIVE" | sha256sum -c -
fi

report_status "installing" "extracting" 55 "Extracting agent artifact"
tar -xzf "$ARCHIVE" -C "$WORKDIR"
SRC=""
if [[ -d "$WORKDIR/agent/qbox_agent" ]]; then
  SRC="$WORKDIR/agent"
elif [[ -d "$WORKDIR/qbox_agent" ]]; then
  SRC="$WORKDIR"
else
  SRC="$(find "$WORKDIR" -maxdepth 3 -type d -name qbox_agent -print -quit | xargs -r dirname)"
fi
[[ -n "$SRC" && -d "$SRC/qbox_agent" ]] || { echo "Archive does not contain qbox_agent package" >&2; exit 3; }

report_status "installing" "installing" 70 "Installing qbox-agent files"
install -d -m 0755 /opt/qbox-agent
rsync -a --delete "$SRC/" /opt/qbox-agent/
if [[ ! -x /opt/qbox-agent/venv/bin/pip ]]; then python3 -m venv /opt/qbox-agent/venv; fi
/opt/qbox-agent/venv/bin/pip install -r /opt/qbox-agent/requirements.txt

if [[ -n "$VERSION" ]]; then
  echo "$VERSION" > /etc/qbox-agent/version
fi

report_status "installing" "restarting" 90 "Restarting qbox-agent service"
systemctl daemon-reload
systemctl restart qbox-agent.service

report_status "success" "success" 100 "qbox-agent updated successfully to ${VERSION:-unknown}"
