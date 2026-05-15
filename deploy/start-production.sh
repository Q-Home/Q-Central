#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -f .env ]] || { echo "Copy .env.production.example to .env first"; exit 1; }
if grep -Eq 'change-me|replace-with' .env; then echo "Refusing to start with default secrets in .env"; exit 1; fi
docker compose -f docker-compose.production.yml up -d --build
docker compose -f docker-compose.production.yml ps
