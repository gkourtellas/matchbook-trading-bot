#!/bin/bash
# Checks if ngrok is running. If not, starts it again.
# Add to cron to run every few minutes, e.g.:
#   */5 * * * * /home/youruser/multi/ngrok_watchdog.sh

if ! pgrep -f "ngrok http 8050" > /dev/null; then
    cd "$(dirname "$0")"
    nohup ngrok http 8050 > ngrok.log 2>&1 &
fi
