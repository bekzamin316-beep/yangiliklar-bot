#!/usr/bin/env bash
# Railway Postgres'dan lokal dump olish (SSH tunnel orqali, public networking'siz).
# Ishlatish: ./scripts/db-dump.sh
# Natija: ~/yangiliklar-bot-backup/db/railway-<sana>.dump  (pg_restore uchun custom format)
set -euo pipefail

source "$HOME/.railway/env"
cd "$(dirname "$0")/.."

PG_BIN="${PG_BIN:-$HOME/pgclient/bin}"
BK="$HOME/yangiliklar-bot-backup/db"
D="$(date +%F)"
mkdir -p "$BK"
DUMP="$BK/railway-$D.dump"

PGPW="$(railway variable list --kv -s Postgres | grep '^PGPASSWORD=' | cut -d= -f2-)"

railway connect Postgres --tunnel-only -P 5433 > /tmp/railway-tunnel.log 2>&1 &
TUNPID=$!
trap 'kill $TUNPID 2>/dev/null || true' EXIT

for _ in $(seq 1 45); do
  grep -qiE 'listening|forwarding|tunnel|ready|5433|press ctrl' /tmp/railway-tunnel.log 2>/dev/null && break
  kill -0 $TUNPID 2>/dev/null || break
  sleep 1
done

PGPASSWORD="$PGPW" "$PG_BIN/pg_dump" -h 127.0.0.1 -p 5433 -U postgres -d railway \
  -Fc --no-owner --no-privileges -f "$DUMP"

echo "Dump tayyor: $DUMP ($(du -h "$DUMP" | cut -f1))"
"$PG_BIN/pg_restore" --list "$DUMP" 2>/dev/null | grep -c 'TABLE DATA' | sed 's/^/  jadvallar: /'
