#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)

set -a
. ${SCRIPT_DIR}/../../.env
set +a

mkdir -p "$SCRIPT_DIR/data/postgres"
mkdir -p "$SCRIPT_DIR/data/redis"
mkdir -p "$SCRIPT_DIR/data/minio"
mkdir -p "$SCRIPT_DIR/data/scrapper"
mkdir -p "$SCRIPT_DIR/data/pio"
cp "$SCRIPT_DIR/pipeline.yml" "$SCRIPT_DIR/data/pipeline.yml"

chown -R 1000:1000 "$SCRIPT_DIR/data"

docker compose -f "$SCRIPT_DIR/docker-compose.yml" --env-file "$SCRIPT_DIR/../../.env" up -d
