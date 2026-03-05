#! /bin/sh

set -e
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
set -a
. ${SCRIPT_DIR}/../../.env
set +a


IMAGE=ghidraheadless-python3
docker build \
  --build-arg BASE_URL="${BASE_URL}" \
  --no-cache ${BUILD_ARGS:+$BUILD_ARGS} -t "$BASE_URL/$IMAGE" -f "$SCRIPT_DIR"/Dockerfile "$SCRIPT_DIR"
docker tag "$BASE_URL/$IMAGE" "$BASE_URL/$IMAGE:$VERSION"
