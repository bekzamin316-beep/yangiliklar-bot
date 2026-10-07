#!/usr/bin/env bash
# Railway env o'zgaruvchilarini lokal zaxiraga nusxalash.
# Ishlatish: ./scripts/backup-env.sh
# Natija: ~/yangiliklar-bot-backup/env-{bot,postgres,redis}-<sana>.env + render.env
set -euo pipefail

source "$HOME/.railway/env"
cd "$(dirname "$0")/.."

BK="$HOME/yangiliklar-bot-backup"
D="$(date +%F)"
mkdir -p "$BK"

railway variable list --kv -s yangiliklar-bot > "$BK/env-bot-$D.env"
railway variable list --kv -s Postgres         > "$BK/env-postgres-$D.env"
railway variable list --kv -s Redis            > "$BK/env-redis-$D.env"

# Render/WS uchun tayyor fayl (DB/Redis — provider stringi bilan almashtiriladi)
grep -E '^[A-Z_]+=' "$BK/env-bot-$D.env" \
  | grep -vE '^(DATABASE_URL|REDIS_URL)=' > "$BK/render.env"
printf 'DB_TYPE=postgres\nDATABASE_URL=PASTE_NEON_CONNECTION_STRING_HERE\nREDIS_URL=\n' >> "$BK/render.env"

chmod 600 "$BK"/env-*-"$D".env "$BK/render.env"
echo "Zaxira tayyor: $BK/env-*-$D.env va $BK/render.env"
