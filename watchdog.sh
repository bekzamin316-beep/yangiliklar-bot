#!/bin/bash
# Crypto News Bot — watchdog: checks every 5 min, restarts if dead

BOT_DIR="/home/abdujalol/crypto-news-bot"
PID_FILE="$BOT_DIR/bot.pid"
WATCHDOG_LOG="$BOT_DIR/watchdog.log"

cd "$BOT_DIR"

# Check if bot is running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        # Bot alive — check log for recent activity (any update in last 10 min)
        LAST_ACTIVITY=$(tail -100 "$BOT_DIR/bot.log" 2>/dev/null | grep -oP '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' | tail -1)
        if [ -n "$LAST_ACTIVITY" ]; then
            echo "[$(date)] Bot alive (PID $PID), last activity: $LAST_ACTIVITY" >> "$WATCHDOG_LOG"
        else
            echo "[$(date)] Bot alive (PID $PID), no recent activity found" >> "$WATCHDOG_LOG"
        fi
        exit 0
    fi
fi

# Also check by process name
if pgrep -f "python -m src.main" > /dev/null; then
    PID=$(pgrep -f "python -m src.main")
    echo "$PID" > "$PID_FILE"
    echo "[$(date)] Bot alive (found by pgrep, PID $PID), updated PID file" >> "$WATCHDOG_LOG"
    exit 0
fi

# Bot is dead — restart
echo "[$(date)] Bot NOT running! Restarting..." >> "$WATCHDOG_LOG"
bash "$BOT_DIR/restart.sh" >> "$WATCHDOG_LOG" 2>&1
