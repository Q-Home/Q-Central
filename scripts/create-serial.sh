#!/usr/bin/env bash
set -euo pipefail
SERIAL="${1:?serial required}"; CUSTOMER="${2:-}"; SITE="${3:-}"
: "${Q_CENTRAL_URL:?set Q_CENTRAL_URL}"; : "${Q_CENTRAL_ADMIN_TOKEN:?set Q_CENTRAL_ADMIN_TOKEN}"
curl -fsS -X POST "$Q_CENTRAL_URL/api/serials" -H "Content-Type: application/json" -H "X-Admin-Token: $Q_CENTRAL_ADMIN_TOKEN" -d "{\"serial\":\"$SERIAL\",\"customer\":\"$CUSTOMER\",\"site\":\"$SITE\"}"
echo
