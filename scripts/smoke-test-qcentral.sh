#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${Q_CENTRAL_URL:-http://localhost:8080}}"
ADMIN_USER="${Q_CENTRAL_SMOKE_USER:-admin}"
ADMIN_PASSWORD="${Q_CENTRAL_SMOKE_PASSWORD:-}"
COOKIE_JAR="$(mktemp /tmp/qcentral-smoke-cookie.XXXXXX)"
trap 'rm -f "$COOKIE_JAR"' EXIT

fail() {
  echo "[SMOKE] FAIL: $*" >&2
  exit 1
}

ok() {
  echo "[SMOKE] OK: $*"
}

request_code() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -k -sS -o /tmp/qcentral-smoke-body.txt -w '%{http_code}' \
      -X "$method" \
      -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
      -H 'Content-Type: application/json' \
      --data "$body" \
      "${BASE_URL}${path}"
  else
    curl -k -sS -o /tmp/qcentral-smoke-body.txt -w '%{http_code}' \
      -X "$method" \
      -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
      "${BASE_URL}${path}"
  fi
}

expect_code() {
  local method="$1"
  local path="$2"
  local expected="$3"
  local body="${4:-}"
  local code
  code="$(request_code "$method" "$path" "$body")"
  if [[ "$code" != "$expected" ]]; then
    echo "[SMOKE] Response body for ${method} ${path}:" >&2
    cat /tmp/qcentral-smoke-body.txt >&2 || true
    fail "${method} ${path} returned ${code}, expected ${expected}"
  fi
  ok "${method} ${path} -> ${code}"
}

expect_not_404() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local code
  code="$(request_code "$method" "$path" "$body")"
  if [[ "$code" == "404" ]]; then
    echo "[SMOKE] Response body for ${method} ${path}:" >&2
    cat /tmp/qcentral-smoke-body.txt >&2 || true
    fail "${method} ${path} returned 404"
  fi
  ok "${method} ${path} -> ${code}"
}

echo "[SMOKE] Testing Q-Central at ${BASE_URL}"
expect_code GET /healthz 200

# Public OpenAPI must always exist.
expect_code GET /openapi.json 200

# Caddy may preserve /api or strip /api. Both compatibility route sets must exist.
if [[ -n "$ADMIN_PASSWORD" ]]; then
  LOGIN_BODY="{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASSWORD}\"}"
  expect_code POST /api/auth/login 200 "$LOGIN_BODY"
  expect_code GET /api/auth/me 200
  expect_code GET /api/devices 200
  expect_code GET /api/monitoring/overview 200
  expect_not_404 GET /api/software/agent/releases
  expect_not_404 GET /api/software/jobs

  # Reset cookie and validate stripped variants too.
  : > "$COOKIE_JAR"
  expect_code POST /auth/login 200 "$LOGIN_BODY"
  expect_code GET /auth/me 200
  expect_code GET /devices 200
  expect_code GET /monitoring/overview 200
  expect_not_404 GET /software/agent/releases
  expect_not_404 GET /software/jobs
else
  echo "[SMOKE] Q_CENTRAL_SMOKE_PASSWORD not set; checking route existence only."
  expect_not_404 POST /api/auth/login '{"username":"admin","password":"wrong"}'
  expect_not_404 POST /auth/login '{"username":"admin","password":"wrong"}'
  expect_not_404 GET /api/auth/me
  expect_not_404 GET /auth/me
  expect_not_404 GET /api/devices
  expect_not_404 GET /devices
  expect_not_404 GET /api/monitoring/overview
  expect_not_404 GET /monitoring/overview
  expect_not_404 GET /api/software/agent/releases
  expect_not_404 GET /software/agent/releases
  expect_not_404 GET /api/software/jobs
  expect_not_404 GET /software/jobs
fi

ok "Q-Central smoke tests passed"
