#!/bin/sh
# Madhavbaug — production deploy helper.
# Starts the full stack (build optional). Never deletes volumes or data.
# Usage: infra/scripts/deploy.sh [--build] [--no-build]
set -e

COMPOSE_FILE="infra/docker-compose.yml"
ENV_FILE="${MADHAVBAUG_ENV_FILE:-.env}"
BUILD=0

for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --no-build) BUILD=0 ;;
    *) printf 'unknown argument: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENV_FILE" ]; then
  printf 'env file not found: %s\n' "$ENV_FILE" >&2
  exit 1
fi

COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

if [ "$BUILD" -eq 1 ]; then
  $COMPOSE up -d --build
else
  $COMPOSE up -d
fi

$COMPOSE ps
