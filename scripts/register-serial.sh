#!/usr/bin/env bash
set -euo pipefail
SERIAL="${1:-QBX-2026-0001}"
NAME="${2:-Q-Box Demo}"
CUSTOMER="${3:-Demo Customer}"
SITE="${4:-Lab}"
API="${QBOX_CENTRAL_URL:-http://localhost:8080}"
curl -sS -X POST "$API/api/serials" \
  -H 'content-type: application/json' \
  -d "{\"serial\":\"$SERIAL\",\"name\":\"$NAME\",\"claim_token\":\"dev-claim-token\",\"customer\":\"$CUSTOMER\",\"site\":\"$SITE\"}" | python3 -m json.tool
