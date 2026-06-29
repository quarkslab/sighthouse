#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)

set -a
. ${SCRIPT_DIR}/../../.env
. ${SCRIPT_DIR}/../../.version
set +a

mkdir -p "$SCRIPT_DIR/data/postgres"
mkdir -p "$SCRIPT_DIR/data/redis"
mkdir -p "$SCRIPT_DIR/data/rustfs"
mkdir -p "$SCRIPT_DIR/data/scrapper"
mkdir -p "$SCRIPT_DIR/data/pio"
cp "$SCRIPT_DIR/pipeline.yml" "$SCRIPT_DIR/data/pipeline.yml"

# Ensure data is owned by uid 1000 (used by the containers). Fall back to a
# root container when the current user cannot chown files owned by another uid.
chown -R 1000:1000 "$SCRIPT_DIR/data" 2>/dev/null || \
  docker run --rm -v "$SCRIPT_DIR/data:/data" alpine chown -R 1000:1000 /data

docker compose -f "$SCRIPT_DIR/docker-compose.yml" --env-file "$SCRIPT_DIR/../../.env" --env-file "$SCRIPT_DIR/../../.version" up -d
