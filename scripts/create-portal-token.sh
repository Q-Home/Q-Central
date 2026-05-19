#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOKEN="${1:-}"

if [[ -z "$TOKEN" ]]; then
  TOKEN="$(python3 - <<'PY'
import secrets
print("qcp_" + secrets.token_urlsafe(32))
PY
)"
fi

hash_with_python() {
  TOKEN="$TOKEN" python3 - <<'PY'
import os
import sys

try:
    from passlib.context import CryptContext
except ModuleNotFoundError:
    raise SystemExit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
print(pwd_context.hash(os.environ["TOKEN"]))
PY
}

hash_with_docker() {
  local image_id
  image_id="$(docker build -q "$ROOT_DIR/backend")"
  docker run --rm -e TOKEN="$TOKEN" "$image_id" python - <<'PY'
import os
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
print(pwd_context.hash(os.environ["TOKEN"]))
PY
}

if HASH="$(hash_with_python 2>/dev/null)"; then
  :
elif command -v docker >/dev/null 2>&1; then
  HASH="$(hash_with_docker)"
else
  cat >&2 <<'EOF'
Could not generate bcrypt hash because passlib is not installed and Docker is not available.

Run one of these:
  python3 -m pip install -r backend/requirements.txt
  ./scripts/create-portal-token.sh

or run this script on the Q-Central deploy host with Docker available.
EOF
  exit 1
fi

cat <<EOF
Portal token:
$TOKEN

Set this in Q-Central .env:
Q_CENTRAL_PORTAL_TOKEN_HASH=$HASH

Set this in Q-Portal .env:
QCENTRAL_PORTAL_TOKEN=$TOKEN
EOF
