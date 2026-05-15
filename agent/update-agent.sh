#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: sudo update-agent.sh --url <tar.gz-url> [--sha256 <hex>] [--version <version>]

The archive must contain an agent/ directory or qbox_agent/ package.
This script is designed to be called by qbox-agent itself through a systemd-run wrapper.
USAGE
}

URL=""
SHA256=""
VERSION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="${2:-}"; shift 2 ;;
    --sha256) SHA256="${2:-}"; shift 2 ;;
    --version) VERSION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }
[[ -n "$URL" ]] || { echo "--url is required" >&2; exit 2; }

WORKDIR="$(mktemp -d /tmp/qbox-agent-update.XXXXXX)"
trap 'rm -rf "$WORKDIR"' EXIT
ARCHIVE="$WORKDIR/agent.tar.gz"

curl -fsSL "$URL" -o "$ARCHIVE"
if [[ -n "$SHA256" ]]; then
  echo "$SHA256  $ARCHIVE" | sha256sum -c -
fi

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

install -d -m 0755 /opt/qbox-agent
rsync -a --delete "$SRC/" /opt/qbox-agent/
if [[ ! -x /opt/qbox-agent/venv/bin/pip ]]; then python3 -m venv /opt/qbox-agent/venv; fi
/opt/qbox-agent/venv/bin/pip install -r /opt/qbox-agent/requirements.txt

if [[ -n "$VERSION" ]]; then
  echo "$VERSION" > /etc/qbox-agent/version
fi

systemctl daemon-reload
systemctl restart qbox-agent.service
