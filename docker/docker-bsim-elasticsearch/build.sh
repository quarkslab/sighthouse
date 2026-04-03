#!/bin/sh

set -e
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
set -a
. ${SCRIPT_DIR}/../../.env
set +a


IMAGE=create_bsim_db
docker build \
  --build-arg BASE_URL="${BASE_URL}" \
  --no-cache ${BUILD_ARGS:+$BUILD_ARGS} -t "$BASE_URL/$IMAGE" -f "$SCRIPT_DIR/create-db.docker" "$SCRIPT_DIR"
docker tag "$BASE_URL/$IMAGE" "$BASE_URL/$IMAGE:$VERSION"

IMAGE=elastic_bsim
docker build \
  --build-arg ELASTIC_USERNAME="${ELASTIC_USERNAME}" \
  --build-arg ELASTIC_PASSWORD="${ELASTIC_PASSWORD}" \
  --build-arg BASE_URL="${BASE_URL}" \
  --no-cache ${BUILD_ARGS:+$BUILD_ARGS} -t "$BASE_URL/$IMAGE" -f "$SCRIPT_DIR/elastic_bsim.dockerfile" "$SCRIPT_DIR"
docker tag "$BASE_URL/$IMAGE" "$BASE_URL/$IMAGE:$VERSION"
