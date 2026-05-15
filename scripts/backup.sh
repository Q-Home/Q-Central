#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../deploy"
OUT="backup-qcentral-$(date +%Y%m%d-%H%M%S).tar.gz"
docker run --rm -v qcentral-prod_qcentral-data:/data:ro -v "$PWD:/backup" alpine tar czf "/backup/$OUT" -C /data .
echo "$PWD/$OUT"
