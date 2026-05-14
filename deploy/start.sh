#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose up --build -d
printf '\nQ-Box Central started\n'
printf 'API:    http://localhost:8080\n'
printf 'Docs:   http://localhost:8080/docs\n'
printf 'Web UI: http://localhost:5173\n'
