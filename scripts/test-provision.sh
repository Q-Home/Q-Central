#!/usr/bin/env bash
set -euo pipefail
API="${QBOX_CENTRAL_URL:-http://localhost:8080}"
SERIAL="${1:-QBX-2026-0001}"
curl -sS -X POST "$API/api/provision/request" \
  -H 'content-type: application/json' \
  -d "{\"serial\":\"$SERIAL\",\"claim_token\":\"dev-claim-token\",\"hostname\":\"qbox-test\",\"model\":\"DietPi ARM64\",\"firmware\":\"2026.05.1\",\"zerotier_node_id\":\"abc123\",\"zerotier_ip\":\"10.147.17.44\"}" | python3 -m json.tool
