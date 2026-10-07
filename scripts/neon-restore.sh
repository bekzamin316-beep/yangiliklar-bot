#!/usr/bin/env bash
# Lokal dump faylini Neon (yoki istalgan Postgres) ga ko'chirish.
# Ishlatish: NEON_URL='postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require' \
#            ./scripts/neon-restore.sh [dump-fayl]
set -euo pipefail

PG_BIN="${PG_BIN:-$HOME/pgclient/bin}"
cd "$(dirname "$0")/.."

# NEON_URL majburiy
if [ -z "${NEON_URL:-}" ]; then
  echo "XATO: NEON_URL env ozgaruvchisi kerak — Neon connection string."
  echo "Misol: NEON_URL='postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require' $0"
  exit 1
fi

DUMP="${1:-$(ls -t "$HOME"/yangiliklar-bot-backup/db/railway-*.dump 2>/dev/null | head -1)}"
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "XATO: dump fayli topilmadi (avval scripts/db-dump.sh ishga tushiring)"; exit 1; }

echo "Manba : $DUMP"
echo "Nishon: ${NEON_URL%%:*}://***@${NEON_URL#*@}"

"$PG_BIN/pg_restore" --no-owner --no-privileges --exit-on-error -d "$NEON_URL" "$DUMP"

echo "✅ Restore tugadi — tekshirish uchun:"
echo "   PGPASSWORD=... psql '\$NEON_URL' -c '\\dt' -c 'SELECT count(*) FROM news;'"
