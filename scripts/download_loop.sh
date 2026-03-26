#!/bin/bash
# Download loop with zombie cleanup between runs
PYTHON="c:/Users/kaleb/Documents/murkml/.venv/Scripts/python.exe"
SCRIPT="c:/Users/kaleb/Documents/murkml/scripts/download_batch.py"
LOG="c:/Users/kaleb/Documents/murkml/data/download_loop_log.txt"

echo "=== Download loop started $(date) ===" >> "$LOG"

for i in $(seq 1 30); do
    echo "" >> "$LOG"
    echo "=== ATTEMPT $i at $(date) ===" >> "$LOG"

    # Kill any zombie python processes over 100MB
    tasklist | grep python.exe | awk '{if ($5+0 > 100000) print $2}' | while read pid; do
        taskkill //PID $pid //F 2>/dev/null
    done
    sleep 2

    # Run download
    "$PYTHON" "$SCRIPT" --continuous-only --skip-merge --batch-size 15 >> "$LOG" 2>&1
    EXIT_CODE=$?

    echo "Exit code: $EXIT_CODE" >> "$LOG"

    if [ $EXIT_CODE -eq 0 ]; then
        echo "=== DOWNLOAD COMPLETE $(date) ===" >> "$LOG"
        break
    fi

    echo "Process died, restarting in 10s..." >> "$LOG"
    sleep 10
done
