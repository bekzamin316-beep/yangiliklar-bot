#!/bin/bash

# Backup script for database
set -e

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_CONTAINER="crypto_news_db"

echo "📦 Creating database backup..."

mkdir -p $BACKUP_DIR

docker exec $DB_CONTAINER pg_dump -U postgres crypto_news_bot > $BACKUP_DIR/backup_$DATE.sql

echo "✅ Backup created: $BACKUP_DIR/backup_$DATE.sql"

# Keep only last 7 backups
cd $BACKUP_DIR
ls -t backup_*.sql | tail -n +8 | xargs -r rm
echo "🧹 Old backups cleaned up"
