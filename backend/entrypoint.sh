#!/bin/sh
set -eu

MAX_DB_WAIT="${MAX_DB_WAIT:-60}"
n=0
echo "[entrypoint] waiting for database connection"
until python manage.py check --database default >/dev/null 2>&1; do
    n=$((n + 1))
    if [ "$n" -ge "$MAX_DB_WAIT" ]; then
        echo "[entrypoint] database not reachable after ${MAX_DB_WAIT} attempts" >&2
        exit 1
    fi
    sleep 2
done
echo "[entrypoint] database ready"

# Never generate migrations at runtime. Optional setup commands are explicit and additive.
if [ "${SCHEMA_SETUP_ENABLED:-False}" = "True" ]; then
    echo "[entrypoint] running reviewed additive schema setup"
    python manage.py ensure_openapi_import
    python manage.py ensure_ai_observability
fi

if [ "${RUN_COLLECTSTATIC:-True}" = "True" ]; then
    python manage.py collectstatic --noinput
fi

echo "[entrypoint] starting: $*"
exec "$@"
