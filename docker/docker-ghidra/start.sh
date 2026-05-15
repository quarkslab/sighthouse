#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)

docker compose --env-file ${SCRIPT_DIR}/../../.env --env-file ${SCRIPT_DIR}/../../.version -f "$SCRIPT_DIR/docker-compose.yml" up -d
