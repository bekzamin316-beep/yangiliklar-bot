#!/bin/bash
# Crypto News Bot — restart script with process lock

BOT_DIR="/home/abdujalol/crypto-news-bot"
LOG_FILE="$BOT_DIR/bot.log"
PID_FILE="$BOT_DIR/bot.pid"
PYTHON="$BOT_DIR/venv/bin/python"

cd "$BOT_DIR"

# Kill existing bot if running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[$(date)] Stopping existing bot (PID $OLD_PID)"
        kill "$OLD_PID" 2>/dev/null
        sleep 3
        # Force kill if still running
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID" 2>/dev/null
            sleep 2
        fi
    fi
    rm -f "$PID_FILE"
fi

# Also kill any stray python -m src.main processes
pkill -f "python -m src.main" 2>/dev/null
sleep 2

# Rotate log if too large (>50MB)
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$LOG_SIZE" -gt 52428800 ]; then
        mv "$LOG_FILE" "$LOG_FILE.old"
        echo "[$(date)] Log rotated"
    fi
fi

# Start bot
echo "[$(date)] Starting Crypto News Bot..."
nohup "$PYTHON" -m src.main >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

# Verify it started
sleep 5
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "[$(date)] Bot started successfully (PID $NEW_PID)"
else
    echo "[$(date)] ERROR: Bot failed to start! Check $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
