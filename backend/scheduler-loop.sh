#!/bin/sh
set -eu

INTERVAL="${SCHEDULER_INTERVAL:-300}"
case "$INTERVAL" in
    ''|*[!0-9]*) echo "SCHEDULER_INTERVAL must be a positive integer" >&2; exit 2 ;;
esac

echo "[scheduler] run_all_scheduled_tasks every ${INTERVAL}s"
while true; do
    python manage.py run_all_scheduled_tasks --once || \
        echo "[scheduler] scheduled task pass failed; retrying in ${INTERVAL}s"
    sleep "$INTERVAL"
done
