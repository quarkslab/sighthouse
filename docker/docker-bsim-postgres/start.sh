#!/bin/sh

SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)

docker compose --env-file ${SCRIPT_DIR}/../../.env -f "$SCRIPT_DIR/docker-compose.yml" up -d
