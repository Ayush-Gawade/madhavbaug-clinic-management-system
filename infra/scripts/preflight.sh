#!/bin/sh
# Madhavbaug — read-only production preflight checks.
# Performs no deployment actions, prints no secret values.
# Usage: ./infra/scripts/preflight.sh
set -e

COMPOSE_FILE="infra/docker-compose.yml"
ENV_FILE="${MADHAVBAUG_ENV_FILE:-.env}"
failures=0

say() { printf '\n==> %s\n' "$*"; }
ok() { printf 'PASS: %s\n' "$*"; }
bad() { printf 'FAIL: %s\n' "$*"; failures=$((failures + 1)); }

say "Madhavbaug production preflight"

if command -v docker >/dev/null 2>&1; then
  ok "docker CLI is installed"
else
  bad "docker CLI is not installed"
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  ok "docker compose plugin is installed"
else
  bad "docker compose plugin is missing"
  exit 1
fi

if [ -f "$ENV_FILE" ]; then
  ok "env file present: $ENV_FILE"
else
  bad "env file not found: $ENV_FILE (copy from .env.example and fill real values)"
fi

if docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config --services >/dev/null 2>&1; then
  ok "compose file + env file resolve"
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config --services | sed 's/^/    service: /'
else
  bad "compose file/env file failed to resolve"
fi

exit $failures
