#!/bin/bash

# Monitoring script
echo "📊 Crypto News Bot - System Monitor"
echo "======================================"
echo ""

echo "🐳 Container Status:"
docker compose ps
echo ""

echo "💾 Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
echo ""

echo "📋 Recent Logs (last 20 lines):"
docker compose logs --tail=20 bot
echo ""

echo "🗄️ Database Size:"
docker exec crypto_news_db psql -U postgres -d crypto_news_bot -c "SELECT pg_size_pretty(pg_database_size('crypto_news_bot'));"
echo ""

echo "🔴 Redis Info:"
docker exec crypto_news_redis redis-cli info memory | grep -E "used_memory_human|used_memory_peak_human"
