#!/bin/sh
set -e

# Run database migrations before starting the API when explicitly enabled.
# Workers/beat leave this unset to avoid concurrent migration runs.
if [ "${MIGRATE_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] Applying database migrations..."
  alembic upgrade head
fi

exec "$@"
