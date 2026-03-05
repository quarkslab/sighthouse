#!/bin/sh

set -e
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" >/dev/null 2>&1 && pwd)
set -a
. ${SCRIPT_DIR}/../../.env
set +a
SIGHTHOUSE_DIR="$SCRIPT_DIR/../../"

rm -rf "$SCRIPT_DIR"/build/
mkdir -p "$SCRIPT_DIR"/build/
cp -r "$SIGHTHOUSE_DIR/src" "$SCRIPT_DIR"/build
cp -r "$SIGHTHOUSE_DIR/sighthouse-cli" "$SCRIPT_DIR"/build
cp -r "$SIGHTHOUSE_DIR/sighthouse-core" "$SCRIPT_DIR"/build
cp -r "$SIGHTHOUSE_DIR/sighthouse-pipeline" "$SCRIPT_DIR"/build
cp -r "$SIGHTHOUSE_DIR/sighthouse-client" "$SCRIPT_DIR"/build
cp -r "$SIGHTHOUSE_DIR/sighthouse-frontend" "$SCRIPT_DIR"/build

cd "$SCRIPT_DIR/build/" && find . -name build -exec rm -rf {} + && cd -

cp "$SIGHTHOUSE_DIR/pyproject.toml" "$SCRIPT_DIR"/build

docker build \
  --build-arg BASE_URL="${BASE_URL}" \
  --no-cache ${BUILD_ARGS:+$BUILD_ARGS} -t "$BASE_URL/sighthouse-pipeline" -f "$SCRIPT_DIR"/Dockerfile.pipeline "$SCRIPT_DIR"
docker tag "$BASE_URL/sighthouse-pipeline" "$BASE_URL/sighthouse-pipeline:$VERSION"

docker build \
  --build-arg BASE_URL="${BASE_URL}" \
  --no-cache ${BUILD_ARGS:+$BUILD_ARGS} -t "$BASE_URL/sighthouse-frontend" -f "$SCRIPT_DIR"/Dockerfile.frontend "$SCRIPT_DIR"
docker tag "$BASE_URL/sighthouse-frontend" "$BASE_URL/sighthouse-frontend:$VERSION"

docker build \
  --build-arg BASE_URL="${BASE_URL}" \
  --no-cache ${BUILD_ARGS:+$BUILD_ARGS} -t "$BASE_URL/sighthouse" -f "$SCRIPT_DIR"/Dockerfile.sighthouse "$SCRIPT_DIR"
docker tag "$BASE_URL/sighthouse" "$BASE_URL/sighthouse:$VERSION"
