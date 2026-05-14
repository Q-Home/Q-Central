#!/usr/bin/env bash
set -euo pipefail
DIR="$(dirname "$0")"
"$DIR/register-serial.sh" QBX-2026-0001 "Q-Box Home" "Familie De Smet" "Privéwoning"
"$DIR/register-serial.sh" QBX-2026-0002 "Q-Box Office" "Q-Home" "Kantoor"
"$DIR/register-serial.sh" QBX-2026-0003 "Unclaimed Q-Box" "" "Provisioning"
