#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
PIPELINE_DB="$SCRIPT_DIR/../pipeline/data/postgres"

mkdir -p "$SCRIPT_DIR/data/frontend"
mkdir -p "$SCRIPT_DIR/data/redis"
mkdir -p "$SCRIPT_DIR/data/minio"

if [ -d $PIPELINE_DB ]; then
  cp -r $PIPELINE_DB "$SCRIPT_DIR/data/bsim"
else
  mkdir -p "$SCRIPT_DIR/data/bsim"
fi

chown -R 1000:1000 "$SCRIPT_DIR/data"

docker compose --env-file ${SCRIPT_DIR}/../../.env -f "$SCRIPT_DIR/docker-compose.yml" up -d
